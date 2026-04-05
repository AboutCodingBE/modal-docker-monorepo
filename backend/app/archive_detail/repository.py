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

        # All records are files (no directory records stored)
        total_files_result = await self._session.execute(
            select(func.count()).where(File.archive_id == archive_id)
        )
        total_files = total_files_result.scalar_one()

        # Derive unique folder count from relative_paths
        paths_result = await self._session.execute(
            select(File.relative_path).where(File.archive_id == archive_id)
        )
        all_paths = [row[0] for row in paths_result.all()]
        folders = _unique_folders(all_paths)
        total_folders = len(folders)

        # mime_type distribution
        mime_result = await self._session.execute(
            select(TikaAnalysis.mime_type, func.count().label("count"))
            .join(File, File.id == TikaAnalysis.file_id)
            .where(
                and_(
                    File.archive_id == archive_id,
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

        return {
            "name": archive.name,
            "root_path": archive.root_path,
            "created_at": archive.created_at.date().isoformat() if archive.created_at else None,
            "total_files": total_files,
            "total_folders": total_folders,
            "mime_types": mime_types,
        }

    async def get_folder(self, archive_id: uuid.UUID, path: str) -> dict:
        # Normalise: strip leading slash → empty string means root
        prefix = path.strip().lstrip("/")

        # Fetch all file ids + relative_paths for this archive
        result = await self._session.execute(
            select(File.id, File.relative_path)
            .where(File.archive_id == archive_id)
        )
        all_files = result.all()

        direct_file_ids = []
        subfolder_names: set[str] = set()

        for file_id, rp in all_files:
            if prefix == "":
                # Root level
                if "/" not in rp:
                    direct_file_ids.append(file_id)
                else:
                    subfolder_names.add(rp.split("/")[0])
            else:
                if rp.startswith(prefix + "/"):
                    remainder = rp[len(prefix) + 1:]
                    if "/" not in remainder:
                        direct_file_ids.append(file_id)
                    else:
                        subfolder_names.add(remainder.split("/")[0])

        display_path = f"/{prefix}" if prefix else "/"

        subfolders = sorted(
            [
                {
                    "name": name,
                    "path": f"{display_path}/{name}" if prefix else f"/{name}",
                }
                for name in subfolder_names
            ],
            key=lambda x: x["name"],
        )

        # mime_types for direct files only
        mime_types = []
        if direct_file_ids:
            mime_result = await self._session.execute(
                select(TikaAnalysis.mime_type, func.count().label("count"))
                .where(
                    and_(
                        TikaAnalysis.file_id.in_(direct_file_ids),
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

        return {
            "path": display_path,
            "direct_file_count": len(direct_file_ids),
            "subfolders": subfolders,
            "mime_types": mime_types,
        }


def _unique_folders(relative_paths: list[str]) -> set[str]:
    """Derives unique folder paths from a flat list of file relative_paths."""
    folders: set[str] = set()
    for rp in relative_paths:
        parts = rp.split("/")
        for i in range(1, len(parts)):
            folders.add("/".join(parts[:i]))
    return folders
