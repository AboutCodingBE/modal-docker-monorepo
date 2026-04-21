import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Summary


class SummaryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, analysis_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Returns True if a summary already exists for this analysis + file (resumability check)."""
        result = await self._session.execute(
            select(Summary.id).where(
                Summary.analysis_id == analysis_id,
                Summary.file_id == file_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_file_summaries_for_folder(
        self, analysis_id: uuid.UUID, folder_id: uuid.UUID
    ) -> list[str]:
        """Returns the result strings of all file summaries whose parent_folder_id is this folder."""
        result = await self._session.execute(
            select(Summary.result).where(
                Summary.analysis_id == analysis_id,
                Summary.parent_folder_id == folder_id,
                Summary.file_id != folder_id,
            )
        )
        return [row for (row,) in result.all() if row]

    async def persist(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        file_id: uuid.UUID | None,
        result: str,
    ) -> None:
        summary = Summary(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=file_id,
            result=result,
        )
        self._session.add(summary)
        await self._session.flush()
