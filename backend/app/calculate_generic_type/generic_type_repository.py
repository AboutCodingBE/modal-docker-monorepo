import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import GenericType


class GenericTypeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def persist(
        self,
        file_id: str,
        archive_id: uuid.UUID,
        generic_type: str,
    ) -> GenericType:
        genericType = GenericType(
            id=uuid.uuid4(),
            file_id=file_id,
            archive_id=archive_id,
            generic_type=generic_type,
            analyzed_at=datetime.now(timezone.utc),
        )
        self._session.add(genericType)
        await self._session.flush()
        return genericType
