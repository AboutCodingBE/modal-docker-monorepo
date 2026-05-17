import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ArchiveAnalysis


class ArchiveAnalysisRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        archive_id: uuid.UUID,
        analysis_type: str,
        model: str,
    ) -> ArchiveAnalysis:
        analysis = ArchiveAnalysis(
            archive_id=archive_id,
            type=analysis_type.upper(),
            date=date.today(),
            model=model,
            status="STARTED",
        )
        self._session.add(analysis)
        await self._session.flush()
        await self._session.refresh(analysis)
        return analysis

    async def update_status(self, analysis_id: uuid.UUID, status: str) -> None:
        result = await self._session.execute(
            select(ArchiveAnalysis).where(ArchiveAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        if analysis:
            analysis.status = status
            await self._session.flush()
