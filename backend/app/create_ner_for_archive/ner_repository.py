import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Ner


class NerRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, analysis_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Returns True if a NER result already exists for this analysis + file (resumability check)."""
        result = await self._session.execute(
            select(Ner.id).where(
                Ner.analysis_id == analysis_id,
                Ner.file_id == file_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def persist(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        file_id: uuid.UUID,
        ner_result: dict,
    ) -> None:
        ner = Ner(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=file_id,
            persons=ner_result["persons"],
            person_count=ner_result["person_count"],
            locations=ner_result["locations"],
            location_count=ner_result["location_count"],
            organisations=ner_result["organisations"],
            organisations_count=ner_result["organisations_count"],
            misc=ner_result["misc"],
            misc_count=ner_result["misc_count"],
        )
        self._session.add(ner)
        await self._session.flush()
