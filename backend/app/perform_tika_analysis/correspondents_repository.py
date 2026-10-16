import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import FileCorrespondent


class CorrespondentsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def bulk_insert(
        self,
        file_id: str,
        archive_id: uuid.UUID,
        correspondents: list[dict],
    ) -> None:
        """Bulk-insert correspondent rows for one file.  Each dict in
        ``correspondents`` must have: role, email, name, position."""
        for c in correspondents:
            self._session.add(
                FileCorrespondent(
                    id=uuid.uuid4(),
                    file_id=uuid.UUID(file_id),
                    archive_id=archive_id,
                    role=c["role"],
                    email=c["email"],
                    name=c["name"],
                    position=c["position"],
                )
            )
        await self._session.flush()
