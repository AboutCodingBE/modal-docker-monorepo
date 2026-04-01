from sqlalchemy import select

from shared.database import get_session
from shared.models import Archive


class ArchiveRepository:
    def get_all(self) -> list[dict]:
        with get_session() as session:
            archives = session.execute(
                select(Archive).order_by(Archive.created_at.desc())
            ).scalars().all()

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
