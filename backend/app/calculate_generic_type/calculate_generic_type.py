import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.calculate_generic_type.file_repository import FileRepository
from app.calculate_generic_type.generic_type_repository import GenericTypeRepository
from app.calculate_generic_type.file_classifier import FileClassifier
from app.analysis import task_tracker
from app.shared.logging_config import log_context
from backend.app.perform_tika_analysis.text_functions import path_filter

_logger = logging.getLogger("app.generictype")
fileclassifier = FileClassifier()


class PerformTikaAnalysis:
    """Flow controller for running Tika analysis on all files in an archive."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._file_repo = FileRepository(session)
        self._generic_type_repo = GenericTypeRepository(session)

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
        await task_tracker.start_task(self._session, task_id)
        await self._session.commit()

        files = await self._file_repo.get_by_archive(archive_id)

        #
        
        processed = 0
        failed_count = 0

        try:
            for file in files:
                
                file_path = file["path"]
                file_name = file["name"]
                file_id = file["id"]
                file_mimetype=file["tika_analysis"]["mime_type"] if file["tika_analysis"] else None
                generic_type = fileclassifier.get_generic_type(file_name,file_mimetype)

                await task_tracker.update_progress(self._session, task_id, processed, failed_count, file_path)
                await self._session.commit()


                try:
                    await self._generic_type_repo.persist(
                        file_id,
                        generic_type
                    )
                    processed += 1
                    _logger.info(f"{log_context(archive_id, file_name)}Extraction saved.")
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file_name)}Failed to persist Generic Type: {e}")
                    failed_count += 1
                    continue

            await task_tracker.update_progress(self._session, task_id, processed, failed_count, None)
            await task_tracker.complete_task(self._session, task_id)
            await self._session.commit()
            _logger.info(f"{log_context(archive_id)}Generic type calculation complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Generic type calculation failed unexpectedly: {e}")
            await task_tracker.fail_task(self._session, task_id)
            await self._session.commit()
