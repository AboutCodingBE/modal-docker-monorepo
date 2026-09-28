import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.entity_topic_autocomplete.repository import EntityTopicAutocompleteRepository

router = APIRouter(prefix="/api/archives", tags=["autocomplete"])


@router.get("/{archive_id}/autocomplete/entities")
async def autocomplete_entities(
    archive_id: uuid.UUID,
    entity_type: str = Query(description="Entity type to scope suggestions (e.g. persons, locations, organisations, misc)"),
    prefix: str = Query(description="Text prefix to match against entity names"),
    db: AsyncSession = Depends(get_db),
):
    if not prefix:
        raise HTTPException(status_code=422, detail="prefix must not be empty")
    repo = EntityTopicAutocompleteRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    suggestions = await repo.autocomplete_entities(archive_id, entity_type, prefix)
    return {"suggestions": suggestions}


@router.get("/{archive_id}/autocomplete/topics")
async def autocomplete_topics(
    archive_id: uuid.UUID,
    prefix: str = Query(description="Text prefix to match against topic labels"),
    db: AsyncSession = Depends(get_db),
):
    if not prefix:
        raise HTTPException(status_code=422, detail="prefix must not be empty")
    repo = EntityTopicAutocompleteRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    suggestions = await repo.autocomplete_topics(archive_id, prefix)
    return {"suggestions": suggestions}
