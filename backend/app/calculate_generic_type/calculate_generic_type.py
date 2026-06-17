import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.calculate_generic_type.file_repository import FileRepository
from app.calculate_generic_type.generic_type_repository import GenericTypeRepository
from app.calculate_generic_type.file_classifier import FileClassifier
from app.analysis import task_tracker
from app.shared.logging_config import log_context

_logger = logging.getLogger("app.generictype")
fileclassifier = FileClassifier()


class CalculateGenericType:
    """Flow controller for running Generic type calculation on all files in an archive.

    Accepts a session_factory rather than a single session so that each unit of
    DB work gets its own short-lived connection. The connection is released
    before every classifier call, preventing pool exhaustion during long analyses.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    def _ensure_single_value(self, value):
        """Reduces lists to their first element; converts empty strings to None."""
        if isinstance(value, list):
            value = value[0] if value else None
        if value == "" or value is None:
            return None
        return str(value).strip()

    def _parse_datetime(self, value) -> datetime | None:
        """Parses a Tika date string into a datetime object, or returns None."""
        raw = self._ensure_single_value(value)
        if raw is None:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    async def execute(self, archive_id: uuid.UUID, task_id: uuid.UUID) -> None:
        try:
            # ── Phase 0: start task and fetch file list ───────────────────────
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)
                files = await FileRepository(session).get_by_archive(archive_id)
                await session.commit()

            processed = 0
            failed_count = 0

            # ── File classification loop ──────────────────────────────────────
            for file in files:
                file_path = file["path"]
                file_name = file["name"]
                file_id = file["id"]

                # Update progress — short session, released before classifier call.
                async with self._session_factory() as session:
                    await task_tracker.update_progress(session, task_id, processed, failed_count, file_path)
                    await session.commit()

                # No DB connection held during classification.
                file_mimetype = file["tika_analysis"]["mime_type"] if file["tika_analysis"] else None
                generic_type = fileclassifier.get_generic_type(file_name, file_mimetype)

                try:
                    async with self._session_factory() as session:
                        await GenericTypeRepository(session).persist(file_id, generic_type)
                        await session.commit()
                    processed += 1
                    _logger.info(f"{log_context(archive_id, file_name)}Extraction saved.")
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file_name)}Failed to persist Generic Type: {e}")
                    failed_count += 1

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await session.commit()

            _logger.info(f"{log_context(archive_id)}Generic type calculation complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Generic type calculation failed unexpectedly: {e}")
            async with self._session_factory() as session:
                await task_tracker.fail_task(session, task_id)
                await session.commit()
