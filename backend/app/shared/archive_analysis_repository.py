import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ArchiveAnalysis, ArchiveAnalysisStatus

_BLOCKING_STATUSES = (ArchiveAnalysisStatus.STARTED,)


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

    async def delete_existing(self, archive_id: uuid.UUID, analysis_type: str) -> None:
        """Deletes all archive_analysis rows for this (archive_id, type),
        regardless of status. ON DELETE CASCADE on summary/ner/topic_detection's
        analysis_id automatically wipes their rows too — no separate deletes
        needed. Caller must ensure no STARTED row exists for this type first
        (already guaranteed by the blocking_types check in start_analysis).
        """
        await self._session.execute(
            delete(ArchiveAnalysis).where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.type == analysis_type,
            )
        )

    async def get_blocking_types(self, archive_id: uuid.UUID) -> set[str]:
        """Types with a STARTED ArchiveAnalysis for this archive.

        Values are uppercase (matching AnalysisType enum values), for
        case-normalized comparison against incoming request types.
        """
        result = await self._session.execute(
            select(ArchiveAnalysis.type).where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.status.in_(_BLOCKING_STATUSES),
            )
        )
        return {t.value for t in result.scalars().all()}
