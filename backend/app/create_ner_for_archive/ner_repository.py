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
        def _to_jsonb(strings: list[str]) -> list[dict]:
            return [{"entity": s, "count": 1} for s in strings]

        ner = Ner(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=file_id,
            persons=_to_jsonb(ner_result.get("persons", [])),
            locations=_to_jsonb(ner_result.get("locations", [])),
            organisations=_to_jsonb(ner_result.get("organisations", [])),
            misc=_to_jsonb(ner_result.get("misc", [])),
        )
        self._session.add(ner)
        await self._session.flush()

    async def get_entities_for_folder(
        self,
        analysis_id: uuid.UUID,
        folder_id: uuid.UUID,
        top_n: int = settings.ner_folder_top_n,
    ) -> dict:
        params = {"folder_id": folder_id, "analysis_id": analysis_id, "top_n": top_n}
        result = {}
        for category in ("persons", "locations", "organisations", "misc"):
            rows = await self._session.execute(
                text(
                    f"SELECT elem->>'entity' AS entity, SUM((elem->>'count')::int) AS frequency "
                    f"FROM ner n "
                    f"CROSS JOIN LATERAL jsonb_array_elements(n.{category}) elem "
                    "WHERE n.parent_folder_id = :folder_id AND n.analysis_id = :analysis_id "
                    "GROUP BY entity "
                    "ORDER BY frequency DESC "
                    "LIMIT :top_n"
                ),
                params,
            )
            result[category] = [
                {"entity": row.entity, "count": row.frequency} for row in rows
            ]
        return result

    async def persist_folder(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        folder_id: uuid.UUID,
        entities: dict,
    ) -> None:
        ner = Ner(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=folder_id,
            persons=entities.get("persons", []),
            locations=entities.get("locations", []),
            organisations=entities.get("organisations", []),
            misc=entities.get("misc", []),
        )
        self._session.add(ner)
        await self._session.flush()
