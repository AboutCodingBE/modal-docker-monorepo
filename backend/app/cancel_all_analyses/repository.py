from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ArchiveAnalysis, ArchiveAnalysisStatus, AnalysisTask


class CancelAllAnalysesRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def cancel_running_analyses(self) -> int:
        """Cancel all ArchiveAnalysis records with status STARTED. Returns row count."""
        result = await self._session.execute(
            update(ArchiveAnalysis)
            .where(ArchiveAnalysis.status == ArchiveAnalysisStatus.STARTED)
            .values(status=ArchiveAnalysisStatus.CANCELLED)
        )
        return result.rowcount

    async def cancel_running_tasks(self) -> int:
        """Cancel all AnalysisTask records with status pending or running. Returns row count."""
        result = await self._session.execute(
            update(AnalysisTask)
            .where(AnalysisTask.status.in_(["pending", "running"]))
            .values(status="cancelled")
        )
        return result.rowcount
