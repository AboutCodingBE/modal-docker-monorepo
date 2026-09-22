import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import AgentExportError, write_export_files
from app.export_archive.csv_builder import build_export_csv
from app.export_archive.export_data_repository import ExportDataRepository
from app.export_archive.json_builder import build_export_json
from app.shared.export_settings_service import get_or_initialize_export_settings
from app.shared.models import Archive

ExportFormat = Literal["csv", "json"]


class ExportArchive:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, archive_id: uuid.UUID, export_format: ExportFormat) -> str:
        # Fetch the archive for the JSON header and name
        result = await self._session.execute(select(Archive).where(Archive.id == archive_id))
        archive = result.scalar_one()

        # Auto-computes and persists default_export_path via the agent if not yet set
        export_settings = await get_or_initialize_export_settings(self._session)

        rows = await ExportDataRepository(self._session).get_export_rows(
            archive_id, export_settings.content_char_limit
        )

        # Only the requested format is built — the other builder is never called
        if export_format == "csv":
            filename = "export.csv"
            content = build_export_csv(rows)
        else:
            filename = "export.json"
            archive_header = {
                "id": str(archive.id),
                "name": archive.name,
                "root_path": archive.root_path,
                "created_at": archive.created_at.isoformat() if archive.created_at else None,
            }
            content = build_export_json(archive_header, rows)

        subfolder_name = f"{archive.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return await write_export_files(
            export_settings.default_export_path,
            subfolder_name,
            [{"filename": filename, "content": content}],
        )
