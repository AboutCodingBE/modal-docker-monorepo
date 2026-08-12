import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, ArchiveAnalysis, ArchiveAnalysisStatus


class DeleteArchiveRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def cancel_running_analyses(self, archive_id: uuid.UUID) -> None:
        await self._session.execute(
            update(ArchiveAnalysis)
            .where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.status == ArchiveAnalysisStatus.STARTED,
            )
            .values(status=ArchiveAnalysisStatus.CANCELLED)
        )

    async def delete_archive(self, archive_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Archive).where(Archive.id == archive_id)
        )

    async def commit(self) -> None:
        await self._session.commit()
