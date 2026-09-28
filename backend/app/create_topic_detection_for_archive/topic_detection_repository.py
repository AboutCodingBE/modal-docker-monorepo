import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.models import TopicDetection


class TopicDetectionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, analysis_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Returns True if a TopicDetection result already exists for this analysis + file (resumability check)."""
        result = await self._session.execute(
            select(TopicDetection.id).where(
                TopicDetection.analysis_id == analysis_id,
                TopicDetection.file_id == file_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_all_for_analysis(self, analysis_id: uuid.UUID) -> list[TopicDetection]:
        """Alle TopicDetection-rijen van deze analyse — zowel bestanden als folder-
        aggregaten (persist_folder zet ook een rij weg, met file_id verwijzend naar
        een map). Gebruikt door CreateTagIndexForArchive om de tag_index te vullen.

        LET OP: laadt alle TopicDetection-rijen van de analyse in één keer in het
        geheugen (result.scalars().all()) — zie de gelijkaardige noot bij
        NerRepository.get_all_for_analysis(). Aandachtspunt voor later bij zeer
        grote archieven: een lazy/streaming iterator i.p.v. alles materialiseren.
        """
        result = await self._session.execute(
            select(TopicDetection).where(TopicDetection.analysis_id == analysis_id)
        )
        return list(result.scalars().all())

    async def persist(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        file_id: uuid.UUID,
        topics: list[str],
    ) -> None:
        topic_detection = TopicDetection(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=file_id,
            topics=[{"topic": t, "count": 1} for t in topics],
        )
        self._session.add(topic_detection)
        await self._session.flush()

    async def get_topics_for_folder(
        self,
        analysis_id: uuid.UUID,
        folder_id: uuid.UUID,
        top_n: int = settings.topic_folder_top_n,
    ) -> list[dict]:
        rows = await self._session.execute(
            text(
                "SELECT elem->>'topic' AS topic, SUM((elem->>'count')::int) AS frequency "
                "FROM topic_detection "
                "CROSS JOIN LATERAL jsonb_array_elements(topics) elem "
                "WHERE parent_folder_id = :folder_id AND analysis_id = :analysis_id "
                "GROUP BY topic ORDER BY frequency DESC LIMIT :top_n"
            ),
            {"folder_id": folder_id, "analysis_id": analysis_id, "top_n": top_n},
        )
        return [{"topic": row.topic, "count": row.frequency} for row in rows]

    async def persist_folder(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        folder_id: uuid.UUID,
        topics: list[dict],
    ) -> None:
        topic_detection = TopicDetection(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=folder_id,
            topics=topics,
        )
        self._session.add(topic_detection)
        await self._session.flush()
