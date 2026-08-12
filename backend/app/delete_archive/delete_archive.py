import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.delete_archive.repository import DeleteArchiveRepository


class DeleteArchive:
    def __init__(self, session: AsyncSession):
        self._repo = DeleteArchiveRepository(session)

    async def execute(self, archive_id: uuid.UUID) -> bool:
        archive = await self._repo.get_archive(archive_id)
        if archive is None:
            return False

        await self._repo.cancel_running_analyses(archive_id)
        await self._repo.delete_archive(archive_id)
        await self._repo.commit()
        return True
