import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.create_ner_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_ner_for_archive.file_repository import FileRepository
from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository
from app.shared.logging_config import log_context

_logger = logging.getLogger("app")

_MAX_CONSECUTIVE_FAILURES = 5


class CreateTopicDetectionForArchive:
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
                files = await FileRepository(session).get_files_with_tika_content(archive_id)
                await task_tracker.update_total_files(session, task_id, len(files))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # ── File NER loop ─────────────────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check if already processed and update progress — short session,
                # released before the NER call below.
                async with self._session_factory() as session:
                    if await NerRepository(session).exists(archive_analysis_id, file_id):
                        processed += 1
                        continue
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, file["relative_path"]
                    )
                    await session.commit()

                # No DB connection held during the spaCy call.
                try:
                    text = file["content"] or ""
                    ner_result = await asyncio.to_thread(run_ner, text, model)
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

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(f"{log_context(archive_id)}NER complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}NER task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()
