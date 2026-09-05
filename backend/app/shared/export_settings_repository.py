from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ExportSettings


class ExportSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self) -> ExportSettings:
        result = await self._session.execute(select(ExportSettings).limit(1))
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            raise RuntimeError("export_settings row missing — expected exactly one row, seeded by migration")
        return settings_row

    async def update(self, default_export_path: str | None, content_char_limit: int) -> ExportSettings:
        settings_row = await self.get()
        settings_row.default_export_path = default_export_path
        settings_row.content_char_limit = content_char_limit
        await self._session.flush()
        return settings_row
