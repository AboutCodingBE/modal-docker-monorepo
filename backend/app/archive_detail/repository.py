import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, File, TikaAnalysis


class ArchiveDetailRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def get_stats(self, archive_id: uuid.UUID) -> dict:
        archive = await self.get_archive(archive_id)

        counts_result = await self._session.execute(
            select(
                func.count().filter(File.is_directory == False).label("total_files"),
                func.count().filter(File.is_directory == True).label("total_folders"),
            ).where(File.archive_id == archive_id)
        )
        row = counts_result.one()

        mime_result = await self._session.execute(
            select(TikaAnalysis.mime_type, func.count().label("count"))
            .join(File, File.id == TikaAnalysis.file_id)
            .where(
                and_(
                    File.archive_id == archive_id,
                    File.is_directory == False,
                    TikaAnalysis.mime_type.isnot(None),
                )
            )
            .group_by(TikaAnalysis.mime_type)
            .order_by(func.count().desc())
        )

        return {
            "name": archive.name,
            "root_path": archive.root_path,
            "created_at": archive.created_at.date().isoformat() if archive.created_at else None,
            "total_files": row.total_files,
            "total_folders": row.total_folders,
            "mime_types": [
                {"mime_type": r.mime_type, "count": r.count}
                for r in mime_result.all()
            ],
        }

    async def get_folder(self, archive_id: uuid.UUID, path: str) -> dict:
        # Normalise: strip leading slash → empty string means root
        prefix = path.strip().lstrip("/")

        # Find the folder record (root = relative_path == "")
        folder_result = await self._session.execute(
            select(File).where(
                and_(
                    File.archive_id == archive_id,
                    File.is_directory == True,
                    File.relative_path == prefix,
                )
            )
        )
        folder = folder_result.scalar_one_or_none()

        # Root level: parent_id IS NULL; subfolders: parent_id == folder.id
        if prefix == "":
            parent_filter = File.parent_id.is_(None)
        elif folder is None:
            return {
                "path": f"/{prefix}",
                "direct_file_count": 0,
                "subfolders": [],
                "mime_types": [],
            }
        else:
            parent_filter = File.parent_id == folder.id

        children_result = await self._session.execute(
            select(File).where(
                and_(
                    File.archive_id == archive_id,
                    parent_filter,
                )
            )
        )
        children = children_result.scalars().all()

        direct_files = [c for c in children if not c.is_directory]
        subfolders = sorted(
            [c for c in children if c.is_directory],
            key=lambda f: f.name,
        )

        subfolder_list = [
            {"name": sf.name, "path": f"/{sf.relative_path}"}
            for sf in subfolders
        ]

        # mime_types for direct files only
        file_ids = [f.id for f in direct_files]
        mime_types = []
        if file_ids:
            mime_result = await self._session.execute(
                select(TikaAnalysis.mime_type, func.count().label("count"))
                .where(
                    and_(
                        TikaAnalysis.file_id.in_(file_ids),
                        TikaAnalysis.mime_type.isnot(None),
                    )
                )
                .group_by(TikaAnalysis.mime_type)
                .order_by(func.count().desc())
            )
            mime_types = [
                {"mime_type": r.mime_type, "count": r.count}
                for r in mime_result.all()
            ]

        display_path = f"/{prefix}" if prefix else "/"

        return {
            "path": display_path,
            "direct_file_count": len(direct_files),
            "subfolders": subfolder_list,
            "mime_types": mime_types,
        }
