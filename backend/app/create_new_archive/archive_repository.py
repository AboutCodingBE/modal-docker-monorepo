from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive


class ArchiveRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def persist(self, name: str, root_path: str) -> Archive:
        archive = Archive(name=name, root_path=root_path)
        self._session.add(archive)
        await self._session.flush()
        return archive

    async def update_status(self, archive: Archive, status: str, error_message: str | None = None) -> None:
        archive.analysis_status = status
        if status == "in_progress":
            archive.analysis_started_at = datetime.now(timezone.utc)
        elif status in ("completed", "failed"):
            archive.analysis_completed_at = datetime.now(timezone.utc)
        if error_message is not None:
            archive.error_message = error_message

    async def update_statistics(self, archive: Archive, file_count: int, directory_count: int, total_size_bytes: int) -> None:
        archive.file_count = file_count
        archive.directory_count = directory_count
        archive.total_size_bytes = total_size_bytes
