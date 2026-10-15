import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_

from app.shared.models import File


def parse_cursor_value(sort_by: str, cursor_value: str | None) -> Any:
    if cursor_value is None:
        return None
    if sort_by == "content_created_at":
        return datetime.fromisoformat(cursor_value)
    return cursor_value


def build_cursor_condition(
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
