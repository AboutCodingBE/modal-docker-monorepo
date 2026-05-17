import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TikaAnalysis


class FileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_files_with_tika_content(self, archive_id: uuid.UUID) -> list[dict]:
        """Returns non-directory files that have at least 30 words of Tika-extracted text."""
        result = await self._session.execute(
            select(File, TikaAnalysis)
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                File.archive_id == archive_id,
                File.is_directory == False,  # noqa: E712
                TikaAnalysis.content.isnot(None),
                TikaAnalysis.word_count >= 30,
            )
        )
        return [
            {
                "id": f.id,
                "name": f.name,
                "relative_path": f.relative_path,
                "parent_id": f.parent_id,
                "content": t.content,
            }
            for f, t in result.all()
        ]
