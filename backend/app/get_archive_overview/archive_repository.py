from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, ArchiveAnalysis, ArchiveAnalysisStatus

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

        completed_by_archive = await self._get_completed_types_by_archive()

        return [
            {
                "id": str(a.id),
                "name": a.name,
                "date": a.created_at.date().isoformat() if a.created_at else "",
                "files": a.file_count,
                "status": _STATUS_MAP.get(a.analysis_status, "ingested"),
                "completed_analysis_types": sorted(completed_by_archive.get(a.id, set())),
            }
            for a in archives
        ]

    async def _get_completed_types_by_archive(self) -> dict:
        """One query for all archives: archive_id -> set of completed type strings.

        Values stay uppercase (AnalysisType enum value), matching the casing
        used by analysis_configuration.type, so the frontend can compare the
        two lists directly.
        """
        result = await self._session.execute(
            select(ArchiveAnalysis.archive_id, ArchiveAnalysis.type)
            .where(ArchiveAnalysis.status == ArchiveAnalysisStatus.COMPLETED)
            .distinct()
        )
        completed_by_archive: dict = {}
        for archive_id, analysis_type in result.all():
            completed_by_archive.setdefault(archive_id, set()).add(analysis_type.value)
        return completed_by_archive
