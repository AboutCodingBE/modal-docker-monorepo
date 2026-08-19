from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ProcessingSettings


class ProcessingSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self) -> ProcessingSettings:
        """Returns the single processing_settings row. Always exists (seeded by migration)."""
        result = await self._session.execute(select(ProcessingSettings).limit(1))
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            raise RuntimeError("processing_settings row missing — expected exactly one row, seeded by migration")
        return settings_row

    async def update(
        self,
        summary_char_limit: int,
        topic_char_limit: int,
        ner_llm_char_limit: int,
        minimum_text_length: int,
    ) -> ProcessingSettings:
        settings_row = await self.get()
        settings_row.summary_char_limit = summary_char_limit
        settings_row.topic_char_limit = topic_char_limit
        settings_row.ner_llm_char_limit = ner_llm_char_limit
        settings_row.minimum_text_length = minimum_text_length
        await self._session.flush()
        return settings_row
