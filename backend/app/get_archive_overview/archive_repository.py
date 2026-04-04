from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive

_STATUS_MAP = {
    "pending": "ingested",
    "in_progress": "in_progress",
    "completed": "analysed",
    "failed": "failed",
}


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
                "date": a.created_at.date().isoformat() if a.created_at else "",
                "files": a.file_count,
                "status": _STATUS_MAP.get(a.analysis_status, "ingested"),
            }
            for a in archives
        ]
