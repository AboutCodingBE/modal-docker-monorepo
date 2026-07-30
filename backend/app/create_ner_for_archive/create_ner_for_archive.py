import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.config import settings
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.shared.analysis_engine_registry import classify_ner_engine, get_llm_provider
from app.shared.llm.provider import LlmProviderUnavailableError
from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_llm_engine import run_ner_llm
from app.create_ner_for_archive.ner_repository import NerRepository
from app.shared.file_repository import FileRepository
from app.shared.logging_config import log_context

_logger = logging.getLogger("app")

_MAX_CONSECUTIVE_FAILURES = 5


class CreateNerForArchive:
    """Flow controller for spaCy NER analysis of all files in an archive.

    Accepts a session_factory rather than a single session so that each unit of
    DB work gets its own short-lived connection. The connection is released
    before every run_ner call, preventing pool exhaustion during long analyses.
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

            engine_kind = classify_ner_engine(model)
            llm_provider = get_llm_provider(engine_kind) if engine_kind != "spacy" else None

            # ── File NER loop ─────────────────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check if already processed and update progress — short session,
                # released before the NER call below.
                already_processed = False
                async with self._session_factory() as session:
                    already_processed = await NerRepository(session).exists(archive_analysis_id, file_id)
                    if not already_processed:
                        await task_tracker.update_progress(
                            session, task_id, processed, failed_count, file["relative_path"]
                        )
                        await session.commit()
                if already_processed:
                    processed += 1
                    continue

                # No DB connection held during the NER call.
                try:
                    text = file["content"] or ""
                    if engine_kind == "spacy":
                        ner_result = await asyncio.to_thread(run_ner, text, model)
                    else:
                        ner_result = await run_ner_llm(
                            text[:settings.ner_llm_char_limit], model, llm_provider
                        )
                except LlmProviderUnavailableError:
                    _logger.error(f"{log_context(archive_id)}LLM provider unavailable — stopping NER")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file['name'])}Failed to run NER: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — NER processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                async with self._session_factory() as session:
                    await NerRepository(session).persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, ner_result
                    )
                    await session.commit()

                processed += 1
                consecutive_failures = 0

            # ── Phase 2: folder aggregation (bottom-up) ───────────────────────
            folders_processed = 0
            for folder in folders:
                folder_id: uuid.UUID = folder["id"]

                async with self._session_factory() as session:
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, folder["relative_path"]
                    )
                    await session.commit()

                try:
                    skip_folder = False
                    async with self._session_factory() as session:
                        entities = await NerRepository(session).get_entities_for_folder(
                            archive_analysis_id, folder_id, settings.ner_folder_top_n
                        )
                        if all(not entities[cat] for cat in ("persons", "locations", "organisations", "misc")):
                            skip_folder = True
                        else:
                            await NerRepository(session).persist_folder(
                                archive_analysis_id, archive_id, folder["parent_id"], folder_id, entities
                            )
                            await session.commit()
                    if skip_folder:
                        processed += 1
                        continue
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, folder['name'])}Failed to aggregate NER for folder: {e}")
                    failed_count += 1
                    processed += 1
                    continue

                folders_processed += 1
                processed += 1

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(
                f"{log_context(archive_id)}NER complete. "
                f"Files processed: {processed - folders_processed}, "
                f"folders aggregated: {folders_processed}, "
                f"failed: {failed_count}"
            )

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}NER task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()
