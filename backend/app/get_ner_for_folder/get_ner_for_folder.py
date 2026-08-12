import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_ner_for_folder.repository import NerForFolderRepository


def _extract_entities(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["entity"] for item in jsonb_list if "entity" in item]


class GetNerForFolder:
    def __init__(self, session: AsyncSession):
        self._repo = NerForFolderRepository(session)

    async def execute(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> dict | None:
        folder = await self._repo.get_folder(archive_id, folder_id)
        if folder is None:
            return None

        row = await self._repo.get_ner_for_folder(folder_id)
        ner, model = row if row else (None, None)

        persons = _extract_entities(ner.persons) if ner else []
        locations = _extract_entities(ner.locations) if ner else []
        organisations = _extract_entities(ner.organisations) if ner else []
        misc = _extract_entities(ner.misc) if ner else []

        return {
            "folder_id": str(folder_id),
            "folder_name": folder.name,
            "model": model,
            "persons": persons,
            "locations": locations,
            "organisations": organisations,
            "misc": misc,
            "total_entities": len(persons) + len(locations) + len(organisations) + len(misc),
        }
