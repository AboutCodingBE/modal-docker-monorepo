from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive


class ArchiveRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all(self) -> list[dict]:
        result = await self._session.execute(
            select(Archive).order_by(Archive.created_at.desc())
        )
        archives = result.scalars().all()

        return [
            {
                "id": str(a.id),
                "name": a.name,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "analysis_status": a.analysis_status,
                "file_count": a.file_count,
            }
            for a in archives
        ]
