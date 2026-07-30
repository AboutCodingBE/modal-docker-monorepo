import uuid

from sqlalchemy import select, update
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

    async def get_all_grouped_by_type(self) -> dict[str, list[AnalysisConfiguration]]:
        """One query, all rows, ordered by type — grouping happens in Python below."""
        result = await self._session.execute(
            select(AnalysisConfiguration).order_by(AnalysisConfiguration.type, AnalysisConfiguration.model)
        )
        grouped: dict[str, list[AnalysisConfiguration]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.type, []).append(row)
        return grouped

    async def get_by_id(self, config_id: uuid.UUID) -> AnalysisConfiguration | None:
        return await self._session.get(AnalysisConfiguration, config_id)

    async def set_defaults(self, rows: list[AnalysisConfiguration]) -> None:
        """Sets each given row as default for its type, clearing any other
        default(s) sharing that type. Caller is responsible for having
        already validated that no two rows share a type. Does not commit.
        """
        for row in rows:
            await self._session.execute(
                update(AnalysisConfiguration)
                .where(
                    AnalysisConfiguration.type == row.type,
                    AnalysisConfiguration.id != row.id,
                )
                .values(is_default=False)
            )
            row.is_default = True
        await self._session.flush()
