import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
            persons_count=ner_result["persons_count"],
            locations=ner_result["locations"],
            locations_count=ner_result["locations_count"],
            organisations=ner_result["organisations"],
            organisations_count=ner_result["organisations_count"],
            misc=ner_result["misc"],
            misc_count=ner_result["misc_count"],
        )
        self._session.add(ner)
        await self._session.flush()

    async def get_entities_for_folder(
        self,
        analysis_id: uuid.UUID,
        folder_id: uuid.UUID,
        top_n: int = settings.ner_folder_top_n,
    ) -> dict:
        result = {}
        for category in ("persons", "locations", "organisations", "misc"):
            rows = await self._session.execute(
                text(
                    f"SELECT UNNEST({category}) AS entity, COUNT(*) AS frequency "
                    "FROM ner "
                    "WHERE parent_folder_id = :folder_id AND analysis_id = :analysis_id "
                    "GROUP BY entity "
                    "ORDER BY frequency DESC "
                    "LIMIT :top_n"
                ),
                {"folder_id": folder_id, "analysis_id": analysis_id, "top_n": top_n},
            )
            result[category] = [
                {"entity": row.entity, "count": row.frequency} for row in rows
            ]
        return result
