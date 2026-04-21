import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
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
    """Flow controller for AI summarization of an archive (files + folders)."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._file_repo = FileRepository(session)
        self._summary_repo = SummaryRepository(session)
        self._analysis_repo = ArchiveAnalysisRepository(session)

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
    ) -> None:
        await task_tracker.start_task(self._session, task_id)
        await self._session.commit()

        try:
            files = await self._file_repo.get_files_with_tika_content(archive_id)
            folders = await self._file_repo.get_subfolders(archive_id)

            await task_tracker.update_total_files(self._session, task_id, len(files) + len(folders))
            await self._session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # ── Phase 1: file summaries ───────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Skip already-summarised files (allows resuming interrupted runs)
                if await self._summary_repo.exists(archive_analysis_id, file_id):
                    processed += 1
                    continue

                await task_tracker.update_progress(
                    self._session, task_id, processed, failed_count, file["relative_path"]
                )
                await self._session.commit()

                try:
                    text = (file["content"] or "")[:1000]
                    result = await generate(model, _file_prompt(text))
                    await self._summary_repo.persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, result
                    )
                    processed += 1
                    consecutive_failures = 0
                except OllamaUnavailableError:
                    print("Ollama service unavailable — stopping summarization")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    print(f"Failed to summarize file {file['name']}: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        print("Repeated failures — processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return

                await self._session.commit()

            # ── Phase 2: folder summaries (summary of summaries) ──────────────
            for folder in folders:
                folder_id: uuid.UUID = folder["id"]

                await task_tracker.update_progress(
                    self._session, task_id, processed, failed_count, folder["relative_path"]
                )
                await self._session.commit()

                folder_summaries = await self._summary_repo.get_file_summaries_for_folder(
                    archive_analysis_id, folder_id
                )
                if not folder_summaries:
                    processed += 1
                    continue

                try:
                    concatenated = "\n".join(folder_summaries)
                    result = await generate(model, _folder_prompt(concatenated))
                    await self._summary_repo.persist(
                        archive_analysis_id, archive_id, folder["parent_id"], folder_id, result
                    )
                    processed += 1
                    consecutive_failures = 0
                except OllamaUnavailableError:
                    print("Ollama service unavailable — stopping summarization")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    print(f"Failed to summarize folder {folder['name']}: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        print("Repeated failures — processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return

                await self._session.commit()

            # ── Completion ────────────────────────────────────────────────────
            await task_tracker.update_progress(self._session, task_id, processed, failed_count, None)
            await task_tracker.complete_task(self._session, task_id)
            await self._analysis_repo.update_status(archive_analysis_id, "COMPLETED")
            await self._session.commit()
            print(f"Summarization complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            print(f"Summarization task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        await task_tracker.fail_task(self._session, task_id)
        await self._analysis_repo.update_status(archive_analysis_id, "FAILED")
        await self._session.commit()
