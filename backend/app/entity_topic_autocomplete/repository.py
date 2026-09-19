import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, FileEntity, FileTopic

SUGGESTION_CAP = 10


class EntityTopicAutocompleteRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def autocomplete_entities(
        self,
        archive_id: uuid.UUID,
        entity_type: str,
        prefix: str,
    ) -> list[str]:
        result = await self._session.execute(
            select(FileEntity.entity_text)
            .where(
                FileEntity.archive_id == archive_id,
                FileEntity.entity_type == entity_type,
                func.unaccent(FileEntity.entity_text).ilike(
                    func.concat(func.unaccent(prefix), "%")
                ),
            )
            .distinct()
            .order_by(FileEntity.entity_text)
            .limit(SUGGESTION_CAP)
        )
        return result.scalars().all()

    async def autocomplete_topics(
        self,
        archive_id: uuid.UUID,
        prefix: str,
    ) -> list[str]:
        result = await self._session.execute(
            select(FileTopic.topic_label)
            .where(
                FileTopic.archive_id == archive_id,
                func.unaccent(FileTopic.topic_label).ilike(
                    func.concat(func.unaccent(prefix), "%")
                ),
            )
            .distinct()
            .order_by(FileTopic.topic_label)
            .limit(SUGGESTION_CAP)
        )
        return result.scalars().all()
