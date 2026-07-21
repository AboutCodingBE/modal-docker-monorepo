import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_topics_for_folder.repository import TopicsForFolderRepository


def _extract_topics(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["topic"] for item in jsonb_list if "topic" in item]


class GetTopicsForFolder:
    def __init__(self, session: AsyncSession):
        self._repo = TopicsForFolderRepository(session)

    async def execute(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> dict | None:
        folder = await self._repo.get_folder(archive_id, folder_id)
        if folder is None:
            return None

        topic_detection = await self._repo.get_topics_for_folder(folder_id)

        topics = _extract_topics(topic_detection.topics) if topic_detection else []

        return {
            "folder_id": str(folder_id),
            "folder_name": folder.name,
            "topics": topics,
            "total_topics": len(topics),
        }
