import asyncio
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.perform_tika_analysis.file_repository import FileRepository
from app.perform_tika_analysis.tika_extractor import TIKA_text_extract
from app.perform_tika_analysis.tika_repository import TikaRepository
from app.perform_tika_analysis.text_functions import normalize_newlines, get_word_count, file_filter, path_filter
from app.analysis import task_tracker


class PerformTikaAnalysis:
    """Flow controller for running Tika analysis on all files in an archive."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._file_repo = FileRepository(session)
        self._tika_repo = TikaRepository(session)

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
        processed = 0
        failed_count = 0

        try:
            for file in files:
                file_path = file["path"]
                file_name = file["name"]
                file_id = file["id"]

                if not (file_filter(file_name) and path_filter(file_path)):
                    print(f"{file_name} is ignored.")
                    continue

                await task_tracker.update_progress(self._session, task_id, processed, failed_count, file_path)
                await self._session.commit()

                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{settings.agent_url}/file-content",
                            params={"path": file_path},
                            timeout=300.0,
                        )
                        resp.raise_for_status()
                        file_content = resp.content
                except Exception as e:
                    print(f"Kon bestand niet ophalen van agent voor {file_name}: {e}")
                    failed_count += 1
                    continue

                tika = await asyncio.to_thread(TIKA_text_extract, file_content)

                if not isinstance(tika, (tuple, list)) or len(tika) < 6:
                    print(f"{file_name}: invalid Tika output, skipping.")
                    failed_count += 1
                    continue

                mime_type = self._ensure_single_value(tika[0])
                content = tika[1]
                parsers = tika[2]
                tika_parser = ", ".join(parsers) if isinstance(parsers, list) else str(parsers)
                lang = self._ensure_single_value(tika[3])
                creation_date = self._parse_datetime(tika[4])
                creator = self._ensure_single_value(tika[5])

                if content and len(str(content).strip()) > 0:
                    clean_content = normalize_newlines(content)
                    word_count = get_word_count(clean_content)
                else:
                    clean_content = None
                    word_count = 0

                try:
                    await self._tika_repo.persist(
                        file_id,
                        mime_type,
                        tika_parser,
                        clean_content,
                        lang,
                        word_count,
                        creator,
                        creation_date,
                    )
                    processed += 1
                    print(f"{file_name} written to {file_id}")
                except Exception as e:
                    print(f"Fout bij opslaan van {file_name}: {e}")
                    failed_count += 1
                    continue

            await task_tracker.update_progress(self._session, task_id, processed, failed_count, None)
            await task_tracker.complete_task(self._session, task_id)
            await self._session.commit()
            print(f"Done. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            print(f"Tika analysis failed: {e}")
            await task_tracker.fail_task(self._session, task_id)
            await self._session.commit()
