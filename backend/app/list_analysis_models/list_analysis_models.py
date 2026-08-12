from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository


class ListAnalysisModels:
    def __init__(self, session: AsyncSession):
        self._repo = AnalysisConfigurationRepository(session)

    async def execute(self) -> dict[str, list[dict]]:
        grouped = await self._repo.get_all_grouped_by_type()
        return {
            analysis_type: [
                {"id": str(row.id), "model": row.model, "is_default": row.is_default} for row in rows
            ]
            for analysis_type, rows in grouped.items()
        }
