import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File

class FileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_archive(self, archive_id: uuid.UUID) -> list[dict]:
        """Returns all non-directory files belonging to the given archive, including Tika MIME type."""
        result = await self._session.execute(
            select(File)
            .options(selectinload(File.tika_analysis))
            .where(
                File.archive_id == archive_id,
                File.is_directory == False,  # noqa: E712
            )
        )
        files = result.scalars().all()
        return [
            {
                "path": str(f.full_path),
                "name": str(f.name),
                "id": str(f.id),
                "tika_analysis": {"mime_type": f.tika_analysis.mime_type} if f.tika_analysis else None,
            }
            for f in files
        ]
