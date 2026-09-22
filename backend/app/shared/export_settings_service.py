from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import get_default_export_path
from app.shared.export_settings_repository import ExportSettingsRepository
from app.shared.models import ExportSettings


async def get_or_initialize_export_settings(session: AsyncSession) -> ExportSettings:
    """Returns the export_settings row, auto-computing and persisting
    default_export_path via the agent if it's still unset. Callers should
    use this instead of ExportSettingsRepository.get() directly whenever
    default_export_path is actually needed.
    """
    repo = ExportSettingsRepository(session)
    export_settings = await repo.get()

    if not export_settings.default_export_path:
        computed_default = await get_default_export_path()
        export_settings = await repo.update(computed_default, export_settings.content_char_limit)
        await session.commit()

    return export_settings
