import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.shared.logging_config import log_context

_logger = logging.getLogger("app.summary")

from app.create_summaries_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_summaries_for_archive.file_repository import FileRepository
from app.create_summaries_for_archive.ollama_client import OllamaUnavailableError, generate
from app.create_summaries_for_archive.summary_repository import SummaryRepository

_MAX_CONSECUTIVE_FAILURES = 5


def _file_prompt(text: str) -> str:
    return (
        "Geef een antwoord in een korte zin. Geef GEEN verdere toelichting bij je antwoord.\n\n"
        f"Vat deze tekst samen in het Nederlands:\n\n{text}"
    )


def _folder_prompt(text: str) -> str:
    return (
        "Geef een antwoord in een korte zin. Geef GEEN verdere toelichting bij je antwoord.\n\n"
        f"Vat deze samenvattingen samen in het Nederlands:\n\n{text}"
    )


class CreateSummariesForArchive:
    """Flow controller for AI summarization of an archive (files + folders).

    Accepts a session_factory rather than a single session so that each unit of
    DB work gets its own short-lived connection. The connection is released
    before every Ollama call, preventing pool exhaustion during long analyses.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
    ) -> None:
        try:
            # ── Phase 0: start task and fetch file list ───────────────────────
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)
                file_repo = FileRepository(session)
                files = await file_repo.get_files_with_tika_content(archive_id)
                folders = await file_repo.get_all_folders(archive_id)
                await task_tracker.update_total_files(session, task_id, len(files) + len(folders))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # ── Phase 1: file summaries ───────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check if already summarised and update progress — short session,
                # released before the Ollama call below.
                async with self._session_factory() as session:
                    if await SummaryRepository(session).exists(archive_analysis_id, file_id):
                        processed += 1
                        continue
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, file["relative_path"]
                    )
                    await session.commit()

                # No DB connection held during the Ollama HTTP call.
                try:
                    text = (file["content"] or "")[:1000]
                    result = await generate(model, _file_prompt(text))
                except OllamaUnavailableError:
                    _logger.error(f"{log_context(archive_id)}Ollama service unavailable — stopping summarization")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file['name'])}Failed to summarize file: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                async with self._session_factory() as session:
                    await SummaryRepository(session).persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, result
                    )
                    await session.commit()

                processed += 1
                consecutive_failures = 0

            # ── Phase 2: folder summaries (summary of summaries) ──────────────
            for folder in folders:
                folder_id: uuid.UUID = folder["id"]

                # Update progress and fetch existing file summaries — short session,
                # released before the Ollama call.
                async with self._session_factory() as session:
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, folder["relative_path"]
                    )
                    await session.commit()
                    folder_summaries = await SummaryRepository(session).get_file_summaries_for_folder(
                        archive_analysis_id, folder_id
                    )

                if not folder_summaries:
                    processed += 1
                    continue

                # No DB connection held during the Ollama HTTP call.
                try:
                    concatenated = "\n".join(folder_summaries)
                    result = await generate(model, _folder_prompt(concatenated))
                except OllamaUnavailableError:
                    _logger.error(f"{log_context(archive_id)}Ollama service unavailable — stopping summarization")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, folder['name'])}Failed to summarize folder: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                async with self._session_factory() as session:
                    await SummaryRepository(session).persist(
                        archive_analysis_id, archive_id, folder["parent_id"], folder_id, result
                    )
                    await session.commit()

                processed += 1
                consecutive_failures = 0

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(f"{log_context(archive_id)}Summarization complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Summarization task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()
