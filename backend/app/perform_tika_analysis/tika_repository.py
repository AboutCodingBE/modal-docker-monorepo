import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import TikaAnalysis


class TikaRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def persist(
        self,
        file_id: str,
        mime_type: str,
        tika_parser: str,
        content: str,
        language: str,
        word_count: int,
        author: str,
        content_created_at: datetime,
    ) -> TikaAnalysis:
        analysis = TikaAnalysis(
            id=uuid.uuid4(),
            file_id=file_id,
            mime_type=mime_type,
            tika_parser=tika_parser,
            content=content,
            language=language,
            word_count=word_count,
            author=author,
            content_created_at=content_created_at,
            analyzed_at=datetime.now(timezone.utc),
        )
        self._session.add(analysis)
        await self._session.flush()
        return analysis
