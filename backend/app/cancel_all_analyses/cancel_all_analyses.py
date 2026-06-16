import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.cancel_all_analyses.repository import CancelAllAnalysesRepository

_logger = logging.getLogger("app.cancel_all_analyses")


class CancelAllAnalyses:
    def __init__(self, session: AsyncSession):
        self._repo = CancelAllAnalysesRepository(session)
        self._session = session

    async def execute(self) -> dict:
        cancelled_analyses = await self._repo.cancel_running_analyses()
        cancelled_tasks = await self._repo.cancel_running_tasks()
        await self._session.commit()

        _logger.info(
            "Cancel all: %d analyses and %d tasks cancelled",
            cancelled_analyses,
            cancelled_tasks,
        )

        return {
            "cancelled_analyses": cancelled_analyses,
            "cancelled_tasks": cancelled_tasks,
        }
