import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository
from app.shared.models import Archive

from sqlalchemy import select

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
        rows = await TagIndexRepository(self._session).search(
            archive_id, prefix, top_n=SUGGESTION_CAP, source="ner", category=entity_type
        )
        return list(dict.fromkeys(r["value"] for r in rows))

    async def autocomplete_topics(
        self,
        archive_id: uuid.UUID,
        prefix: str,
    ) -> list[str]:
        rows = await TagIndexRepository(self._session).search(
            archive_id, prefix, top_n=SUGGESTION_CAP, source="topic_detection"
        )
        return list(dict.fromkeys(r["value"] for r in rows))
