import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.get_timeline_heatmap.get_timeline_heatmap import TimelineHeatmap

router = APIRouter(prefix="/api", tags=["timeline-heatmap"])


@router.get("/archives/{archive_id}/folders/{folder_id}/timeline-heatmap")
async def get_timeline_heatmap(
    archive_id: uuid.UUID,
    folder_id: uuid.UUID,
    y_dimension: str = Query(default="topics", regex="^(organisations|persons|locations|misc|topics)$"),
    scope: str = Query(default="files", regex="^(files|folders|both)$"),
    range_min: int | None = Query(None),
    range_max: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get timeline heatmap data for a folder.
    
    Args:
        archive_id: Archive ID
        folder_id: Folder ID
        y_dimension: Dimension for Y-axis (organisations, persons, locations, misc, or topics)
        scope: Scope of items to include (files, folders, or both)
        range_min: Optional minimum year for range
        range_max: Optional maximum year for range
    """
    result = await TimelineHeatmap(db).execute(
        archive_id,
        folder_id,
        y_dimension,
        scope,
        range_min,
        range_max,
    )
    
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    return result
