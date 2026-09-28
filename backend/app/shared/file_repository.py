import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TikaAnalysis


class FileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_files_with_tika_content(self, archive_id: uuid.UUID) -> list[dict]:
        """Returns non-directory files that have at least 30 words of Tika-extracted text.

        LET OP: laadt alle matchende bestanden + hun volledige Tika-tekst in één keer
        in het geheugen (result.all()). Voor zeer grote archieven kan dit fors oplopen —
        aandachtspunt voor later: een lazy/streaming iterator (bv. via een server-side
        cursor of paginering) i.p.v. alles in memory te materialiseren.
        """
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

    async def get_all_folders(self, archive_id: uuid.UUID) -> list[dict]:
        """Returns all directories including root, sorted deepest-first.

        LET OP: laadt alle mappen van het archief in één keer in het geheugen
        (result.scalars().all()) — zie de noot bij get_files_with_tika_content().
        """
        result = await self._session.execute(
            select(File).where(
                File.archive_id == archive_id,
                File.is_directory == True,  # noqa: E712
            )
        )
        folders = [
            {
                "id": f.id,
                "name": f.name,
                "relative_path": f.relative_path,
                "parent_id": f.parent_id,
            }
            for f in result.scalars().all()
        ]
        folders.sort(key=lambda f: f["relative_path"].count("/") if f["relative_path"] != "." else -1, reverse=True)
        return folders
