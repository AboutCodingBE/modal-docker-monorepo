import uuid
from datetime import datetime
from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, Ner, TopicDetection, TikaAnalysis


class TimelineHeatmapRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_folder(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> File | None:
        """Verify folder exists."""
        result = await self._session.execute(
            select(File).where(
                and_(
                    File.id == folder_id,
                    File.archive_id == archive_id,
                    File.is_directory == True,  # noqa: E712
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_files_in_folder(
        self, archive_id: uuid.UUID, folder_id: uuid.UUID, include_folders: bool = False
    ) -> list[tuple[uuid.UUID, datetime | None, bool]]:
        """Get all files (and optionally folders) with Tika content creation dates.
        
        Returns: list of (file_id, created_at, is_directory)
        """
        folder_path = await self._session.scalar(
            select(File.full_path).where(
                and_(File.id == folder_id, File.archive_id == archive_id)
            )
        )
        if folder_path is None:
            return []

        # Get all descendant files (not just direct children).
        result = await self._session.execute(
            select(File.id, TikaAnalysis.content_created_at, File.is_directory)
            .outerjoin(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                and_(
                    File.archive_id == archive_id,
                    File.full_path.like(f"{folder_path}%"),
                    File.id != folder_id,  # Exclude the folder itself
                )
            )
        )
        
        if include_folders:
            return result.all()
        else:
            return [(id_, date, is_dir) for id_, date, is_dir in result.all() if not is_dir]

    async def get_ner_entities_for_files(
        self, file_ids: list[uuid.UUID], dimension: str
    ) -> dict[uuid.UUID, list[str]]:
        """Get NER entities for files for a specific dimension.
        
        dimension: 'organisations' | 'persons' | 'locations' | 'misc'
        Returns: dict of file_id -> list of entities
        """
        result = await self._session.execute(
            select(Ner.file_id, getattr(Ner, dimension))
            .where(Ner.file_id.in_(file_ids))
        )
        
        entities_by_file = {}
        for file_id, entities_jsonb in result.all():
            if entities_jsonb:
                entity_names = [item.get("entity") for item in entities_jsonb if "entity" in item]
                entities_by_file[file_id] = entity_names
            else:
                entities_by_file[file_id] = []
        
        return entities_by_file

    async def get_topics_for_files(self, file_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Get topics for files.
        
        Returns: dict of file_id -> list of topics
        """
        result = await self._session.execute(
            select(TopicDetection.file_id, TopicDetection.topics)
            .where(TopicDetection.file_id.in_(file_ids))
        )
        
        topics_by_file = {}
        for file_id, topics_jsonb in result.all():
            if topics_jsonb:
                topic_names = [item.get("topic") for item in topics_jsonb if "topic" in item]
                topics_by_file[file_id] = topic_names
            else:
                topics_by_file[file_id] = []
        
        return topics_by_file

    async def get_years_with_data(self, file_ids: list[uuid.UUID]) -> list[int]:
        """Get years from Tika content creation timestamps only."""
        result = await self._session.execute(
            select(func.distinct(extract("year", TikaAnalysis.content_created_at)))
            .select_from(File)
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                and_(
                    File.id.in_(file_ids),
                    TikaAnalysis.content_created_at.isnot(None),
                )
            )
            .order_by(extract("year", TikaAnalysis.content_created_at))
        )
        
        years = [int(year) for year, in result.all() if year is not None]
        return sorted(years)

    async def get_files_by_year(self, file_ids: list[uuid.UUID]) -> dict[int, list[uuid.UUID]]:
        """Group files by Tika content creation date only.
        
        Returns: dict of year -> list of file_ids
        """
        result = await self._session.execute(
            select(extract("year", TikaAnalysis.content_created_at), File.id)
            .select_from(File)
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(
                and_(
                    File.id.in_(file_ids),
                    TikaAnalysis.content_created_at.isnot(None),
                )
            )
            .order_by(extract("year", TikaAnalysis.content_created_at))
        )
        
        files_by_year = {}
        for year, file_id in result.all():
            if year is not None:
                year_int = int(year)
                if year_int not in files_by_year:
                    files_by_year[year_int] = []
                files_by_year[year_int].append(file_id)
        
        return files_by_year
