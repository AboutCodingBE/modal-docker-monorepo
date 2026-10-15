import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.cursor import build_cursor_condition
from app.shared.models import Archive, File, TikaAnalysis

PAGE_SIZE = 75
MAX_SNIPPETS_PER_FILE = 2
SNIPPET_CONTEXT = 150


class SearchFilesRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        archive_id: uuid.UUID,
        term: str,
        folder_path: str | None,
        cursor_id: uuid.UUID | None,
        cursor_value: str | None,
    ) -> dict:
        conditions = [
            File.archive_id == archive_id,
            File.is_directory == False,
            TikaAnalysis.content.icontains(term, autoescape=True),
        ]

        if folder_path is not None:
            prefix = folder_path.strip().strip("/")
            conditions.append(File.relative_path.like(f"{prefix}/%"))

        if cursor_id is not None and cursor_value is not None:
            cursor_cond = build_cursor_condition(
                sort_col=File.relative_path,
                sort_dir="asc",
                nullable=False,
                cursor_id=cursor_id,
                cursor_value_raw=cursor_value,
                cursor_value_parsed=cursor_value,
            )
            if cursor_cond is not None:
                conditions.append(cursor_cond)

        stmt = (
            select(File.id, File.name, File.relative_path)
            .join(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .where(and_(*conditions))
            .order_by(File.relative_path.asc(), File.id.asc())
            .limit(PAGE_SIZE + 1)
        )

        rows = (await self._session.execute(stmt)).all()

        has_next = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]

        if not rows:
            return {"files": [], "has_next": False, "next_cursor_id": None, "next_cursor_value": None}

        file_ids = [r.id for r in rows]
        snippets_by_file = await self._fetch_snippets(file_ids, term)

        files = []
        for r in rows:
            files.append({
                "id": str(r.id),
                "name": r.name,
                "relative_path": r.relative_path,
                "snippets": snippets_by_file.get(r.id, []),
            })

        next_cursor_id = None
        next_cursor_value = None
        if has_next:
            last = files[-1]
            next_cursor_id = last["id"]
            next_cursor_value = last["relative_path"]

        return {
            "files": files,
            "has_next": has_next,
            "next_cursor_id": next_cursor_id,
            "next_cursor_value": next_cursor_value,
        }

    async def _fetch_snippets(
        self, file_ids: list[uuid.UUID], term: str
    ) -> dict[uuid.UUID, list[dict]]:
        stmt = select(TikaAnalysis.file_id, TikaAnalysis.content).where(
            TikaAnalysis.file_id.in_(file_ids),
            TikaAnalysis.content.isnot(None),
        )
        rows = (await self._session.execute(stmt)).all()

        result: dict[uuid.UUID, list[dict]] = {}
        for file_id, content in rows:
            if content:
                result[file_id] = _extract_snippets(content, term)
        return result


def _extract_snippets(content: str, term: str) -> list[dict]:
    snippets = []
    content_lower = content.lower()
    term_lower = term.lower()
    term_len = len(term)

    search_from = 0
    while len(snippets) < MAX_SNIPPETS_PER_FILE:
        pos = content_lower.find(term_lower, search_from)
        if pos == -1:
            break

        snippet_start = max(0, pos - SNIPPET_CONTEXT)
        snippet_end = min(len(content), pos + term_len + SNIPPET_CONTEXT)
        snippet_text = content[snippet_start:snippet_end]

        snippets.append({
            "text": snippet_text,
            "match_offset": pos,
            "highlight_start": pos - snippet_start,
            "highlight_end": pos - snippet_start + term_len,
        })

        search_from = pos + term_len

    return snippets
