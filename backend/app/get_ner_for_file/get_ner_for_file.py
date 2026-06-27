import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_ner_for_file.repository import NerForFileRepository


class GetNerForFile:
    def __init__(self, session: AsyncSession):
        self._repo = NerForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        ner = await self._repo.get_ner_for_file(file_id)

        persons = ner.persons or [] if ner else []
        locations = ner.locations or [] if ner else []
        organisations = ner.organisations or [] if ner else []
        misc = ner.misc or [] if ner else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "persons": persons,
            "locations": locations,
            "organisations": organisations,
            "misc": misc,
            "total_entities": len(persons) + len(locations) + len(organisations) + len(misc),
        }
