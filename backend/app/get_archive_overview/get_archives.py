from sqlalchemy.ext.asyncio import AsyncSession

from app.get_archive_overview.archive_repository import ArchiveRepository


class GetArchives:
    """Flow controlling function. Delegates to ArchiveRepository."""

    def __init__(self, session: AsyncSession):
        self._repo = ArchiveRepository(session)

    async def execute(self) -> list[dict]:
        return await self._repo.get_all()
