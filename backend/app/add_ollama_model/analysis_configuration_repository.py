from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import AnalysisConfiguration, AnalysisType


class AnalysisConfigurationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def model_exists(self, model: str) -> bool:
        result = await self._session.execute(
            select(AnalysisConfiguration.id).where(AnalysisConfiguration.model == model)
        )
        return result.scalar_one_or_none() is not None

    async def create(self, analysis_type: AnalysisType, model: str, is_default: bool) -> None:
        config = AnalysisConfiguration(type=analysis_type.value, model=model, is_default=is_default)
        self._session.add(config)
        await self._session.flush()
