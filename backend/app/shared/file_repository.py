import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, GenericType, TikaAnalysis

# Sentinel value used in the API to represent files that have no category.
CATEGORY_NONE_SENTINEL = "__none__"


class FileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_files_with_tika_content(
        self,
        archive_id: uuid.UUID,
        categories: list[str] | None = None,
    ) -> list[dict]:
        """Return non-directory files that have at least 30 words of Tika-extracted text.

        When *categories* is provided, only files whose generic_type matches one of
        the listed values are returned.  Use CATEGORY_NONE_SENTINEL ("__none__") to
        include files that have no category row or a null generic_type.
        None (default) means all categories — preserving the previous behaviour.
        """
        query = (
            select(File, TikaAnalysis)
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                File.archive_id == archive_id,
                File.is_directory == False,  # noqa: E712
                TikaAnalysis.content.isnot(None),
                TikaAnalysis.word_count >= 30,
            )
        )

        if categories is not None:
            query = query.outerjoin(GenericType, GenericType.file_id == File.id)
            conditions = []
            non_none = [c for c in categories if c != CATEGORY_NONE_SENTINEL]
            if non_none:
                conditions.append(GenericType.generic_type.in_(non_none))
            if CATEGORY_NONE_SENTINEL in categories:
                conditions.append(GenericType.generic_type.is_(None))
            query = query.where(or_(*conditions)) if conditions else query.where(False)

        result = await self._session.execute(query)
        return [
            {
                "id": f.id,
                "name": f.name,
                "relative_path": f.relative_path,
                "parent_id": f.parent_id,
                "content": t.content,
            }
            for f, t in result.all()
        ]

    async def count_files_with_tika_content(
        self,
        archive_id: uuid.UUID,
        categories: list[str] | None = None,
        min_text_length: int = 0,
    ) -> int:
        """Return the number of files that would be processed by an analysis run.

        Applies the same category and minimum-text-length filters as the runners
        so the start endpoint can refuse a run that would process zero files.
        """
        query = (
            select(func.count(File.id))
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                File.archive_id == archive_id,
                File.is_directory == False,  # noqa: E712
                TikaAnalysis.content.isnot(None),
                TikaAnalysis.word_count >= 30,
            )
        )

        if min_text_length > 0:
            query = query.where(func.length(TikaAnalysis.content) >= min_text_length)

        if categories is not None:
            query = query.outerjoin(GenericType, GenericType.file_id == File.id)
            conditions = []
            non_none = [c for c in categories if c != CATEGORY_NONE_SENTINEL]
            if non_none:
                conditions.append(GenericType.generic_type.in_(non_none))
            if CATEGORY_NONE_SENTINEL in categories:
                conditions.append(GenericType.generic_type.is_(None))
            if not conditions:
                return 0
            query = query.where(or_(*conditions))

        result = await self._session.execute(query)
        return result.scalar() or 0

    async def get_all_folders(self, archive_id: uuid.UUID) -> list[dict]:
        """Return all directories including root, sorted deepest-first."""
        result = await self._session.execute(
            select(File).where(
                File.archive_id == archive_id,
                File.is_directory == True,  # noqa: E712
            )
        )
        folders = [
            {
                "id": f.id,
                "name": f.name,
                "relative_path": f.relative_path,
                "parent_id": f.parent_id,
            }
            for f in result.scalars().all()
        ]
        folders.sort(
            key=lambda f: f["relative_path"].count("/") if f["relative_path"] != "." else -1,
            reverse=True,
        )
        return folders
