import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_file_content.repository import FileContentRepository


class GetFileContent:
    def __init__(self, session: AsyncSession):
        self._repo = FileContentRepository(session)

    async def execute(self, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(file_id)
        if file is None:
            return None

        content = await self._repo.get_tika_content(file_id)

        return {
            "file_id": str(file_id),
            "content": content,
        }
