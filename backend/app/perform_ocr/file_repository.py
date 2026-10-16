import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, File, GenericType, TikaAnalysis


class OcrFileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def get_candidates(self, archive_id: uuid.UUID) -> list[dict]:
        """Return OCR candidate files: images (by generic_type) + PDFs/images (by mime_type)."""
        result = await self._session.execute(
            select(File, TikaAnalysis.mime_type, GenericType.generic_type)
            .outerjoin(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .outerjoin(GenericType, GenericType.file_id == File.id)
            .where(
                File.archive_id == archive_id,
                File.is_directory == False,  # noqa: E712
                or_(
                    GenericType.generic_type == "beeldbestand",
                    TikaAnalysis.mime_type.like("application/pdf%"),
                    TikaAnalysis.mime_type.like("image/%"),
                ),
            )
            .order_by(File.relative_path)
        )
        return [
            {
                "id": str(f.id),
                "relative_path": f.relative_path,
                "size_bytes": f.size_bytes,
                "name": f.name,
            }
            for f, _mime, _gt in result.all()
        ]
