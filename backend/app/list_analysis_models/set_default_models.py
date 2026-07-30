import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository


class DuplicateTypeError(Exception):
    """Raised when two or more ids in the same request share an analysis type."""


class SetDefaultModels:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = AnalysisConfigurationRepository(session)

    async def execute(self, config_ids: list[uuid.UUID]) -> dict[str, list[dict]] | None:
        """Returns the updated grouped models view, or None if any id doesn't exist.
        Raises DuplicateTypeError if two ids share a type.
        """
        rows = []
        for config_id in config_ids:
            row = await self._repo.get_by_id(config_id)
            if row is None:
                return None
            rows.append(row)

        seen_types: set[str] = set()
        for row in rows:
            if row.type in seen_types:
                raise DuplicateTypeError(f"Multiple ids target the same analysis type: {row.type}")
            seen_types.add(row.type)

        await self._repo.set_defaults(rows)
        await self._session.commit()
        return await ListAnalysisModels(self._session).execute()
