import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_ner_for_file.repository import NerForFileRepository


def _extract_entities(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["entity"] for item in jsonb_list if "entity" in item]


class GetNerForFile:
    def __init__(self, session: AsyncSession):
        self._repo = NerForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        row = await self._repo.get_ner_for_file(file_id)
        ner, model = row if row else (None, None)

        persons = _extract_entities(ner.persons) if ner else []
        locations = _extract_entities(ner.locations) if ner else []
        organisations = _extract_entities(ner.organisations) if ner else []
        misc = _extract_entities(ner.misc) if ner else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "model": model,
            "persons": persons,
            "locations": locations,
            "organisations": organisations,
            "misc": misc,
            "total_entities": len(persons) + len(locations) + len(organisations) + len(misc),
        }
