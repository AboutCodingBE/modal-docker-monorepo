import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, asc, desc, nullslast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, File, FileEntity, FileTopic, GenericType, TikaAnalysis

PAGE_SIZE = 75

_VALID_SORT_FIELDS = {"content_created_at", "relative_path", "category", "mime_type"}
_VALID_SORT_DIRS = {"asc", "desc"}


class ListFilesRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def list_files(
        self,
        archive_id: uuid.UUID,
        folder_path: str | None,
        sort_by: str,
        sort_dir: str,
        mime_type_filter: list[str] | None,
        category_filter: list[str] | None,
        language_filter: list[str] | None,
        entities: list[str] | None,
        topics: list[str] | None,
        cursor_id: uuid.UUID | None,
        cursor_value: str | None,
    ) -> dict:
        if sort_by not in _VALID_SORT_FIELDS:
            sort_by = "content_created_at"
        if sort_dir not in _VALID_SORT_DIRS:
            sort_dir = "desc"

        conditions = [
            File.archive_id == archive_id,
            File.is_directory == False,
        ]

        if folder_path is not None:
            prefix = folder_path.strip().strip("/")
            conditions.append(File.relative_path.like(f"{prefix}/%"))

        if mime_type_filter:
            conditions.append(TikaAnalysis.mime_type.in_(mime_type_filter))

        if category_filter:
            conditions.append(GenericType.generic_type.in_(category_filter))

        if language_filter:
            conditions.append(TikaAnalysis.language.in_(language_filter))

        if entities:
            pairs = _parse_entity_params(entities)
            if pairs:
                entity_subq = (
                    select(FileEntity.file_id)
                    .where(
                        FileEntity.archive_id == archive_id,
                        or_(
                            *[
                                and_(
                                    FileEntity.entity_type == etype,
                                    FileEntity.entity_text == etext,
                                )
                                for etype, etext in pairs
                            ]
                        ),
                    )
                )
                conditions.append(File.id.in_(entity_subq))

        if topics:
            topic_subq = (
                select(FileTopic.file_id)
                .where(
                    FileTopic.archive_id == archive_id,
                    FileTopic.topic_label.in_(topics),
                )
            )
            conditions.append(File.id.in_(topic_subq))

        direction = desc if sort_dir == "desc" else asc

        if sort_by == "relative_path":
            sort_col = File.relative_path
            order_clause = [direction(sort_col), direction(File.id)]
            nullable_sort = False
        elif sort_by == "category":
            sort_col = GenericType.generic_type
            order_clause = [nullslast(direction(sort_col)), direction(File.id)]
            nullable_sort = True
        elif sort_by == "mime_type":
            sort_col = TikaAnalysis.mime_type
            order_clause = [nullslast(direction(sort_col)), direction(File.id)]
            nullable_sort = True
        else:  # content_created_at
            sort_col = TikaAnalysis.content_created_at
            order_clause = [nullslast(direction(sort_col)), direction(File.id)]
            nullable_sort = True

        if cursor_id is not None:
            parsed = _parse_cursor_value(sort_by, cursor_value)
            cursor_cond = _build_cursor_condition(
                sort_col, sort_dir, nullable_sort, cursor_id, cursor_value, parsed
            )
            if cursor_cond is not None:
                conditions.append(cursor_cond)

        query = (
            select(
                File,
                TikaAnalysis.mime_type,
                GenericType.generic_type,
                TikaAnalysis.language,
                TikaAnalysis.author,
                TikaAnalysis.content_created_at,
            )
            .outerjoin(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .outerjoin(GenericType, GenericType.file_id == File.id)
            .where(and_(*conditions))
            .order_by(*order_clause)
            .limit(PAGE_SIZE + 1)
        )

        result = await self._session.execute(query)
        rows = result.all()

        has_next = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]

        files = []
        for f, mime, generic, language, author, content_created_at in rows:
            files.append({
                "id": str(f.id),
                "name": f.name,
                "relative_path": f.relative_path,
                "extension": f.extension,
                "size_bytes": f.size_bytes,
                "mime_type": mime,
                "category": generic,
                "language": language,
                "author": author,
                "content_created_at": content_created_at.isoformat() if content_created_at else None,
            })

        next_cursor_id = None
        next_cursor_value = None
        if has_next and files:
            last = files[-1]
            next_cursor_id = last["id"]
            if sort_by == "relative_path":
                next_cursor_value = last["relative_path"]
            elif sort_by == "category":
                next_cursor_value = last["category"]
            elif sort_by == "mime_type":
                next_cursor_value = last["mime_type"]
            else:
                next_cursor_value = last["content_created_at"]

        return {
            "files": files,
            "has_next": has_next,
            "next_cursor_id": next_cursor_id,
            "next_cursor_value": next_cursor_value,
        }


def _parse_entity_params(entities: list[str]) -> list[tuple[str, str]]:
    """Parse structured 'type:text' entity filter params into (entity_type, entity_text) pairs.

    Entries that don't contain ':' are silently dropped.
    """
    pairs = []
    for entry in entities:
        if ":" in entry:
            etype, etext = entry.split(":", 1)
            pairs.append((etype.strip(), etext.strip()))
    return pairs


def _parse_cursor_value(sort_by: str, cursor_value: str | None) -> Any:
    if cursor_value is None:
        return None
    if sort_by == "content_created_at":
        return datetime.fromisoformat(cursor_value)
    return cursor_value


def _build_cursor_condition(
    sort_col: Any,
    sort_dir: str,
    nullable: bool,
    cursor_id: uuid.UUID,
    cursor_value_raw: str | None,
    cursor_value_parsed: Any,
) -> Any:
    """Build the keyset (cursor) WHERE clause for the given sort configuration.

    For nullable sorts (content_created_at, category) with NULLS LAST:
      - If cursor is on a non-null row: remaining rows are those with a smaller/larger
        value, same value but smaller/larger id, or NULL (which always comes after).
      - If cursor is on a null row: remaining rows are other NULLs with a smaller/larger id.

    For non-nullable sorts (relative_path):
      - Standard two-column keyset condition.
    """
    is_desc = sort_dir == "desc"

    if not nullable:
        if cursor_value_parsed is None:
            return None
        if is_desc:
            return or_(
                sort_col < cursor_value_parsed,
                and_(sort_col == cursor_value_parsed, File.id < cursor_id),
            )
        else:
            return or_(
                sort_col > cursor_value_parsed,
                and_(sort_col == cursor_value_parsed, File.id > cursor_id),
            )

    # Nullable sort — NULLS LAST
    if cursor_value_parsed is not None:
        if is_desc:
            return or_(
                sort_col < cursor_value_parsed,
                and_(sort_col == cursor_value_parsed, File.id < cursor_id),
                sort_col.is_(None),
            )
        else:
            return or_(
                sort_col > cursor_value_parsed,
                and_(sort_col == cursor_value_parsed, File.id > cursor_id),
                sort_col.is_(None),
            )
    else:
        # Cursor is in the NULL section
        if is_desc:
            return and_(sort_col.is_(None), File.id < cursor_id)
        else:
            return and_(sort_col.is_(None), File.id > cursor_id)
