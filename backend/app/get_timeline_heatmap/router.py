import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.get_timeline_heatmap.get_timeline_heatmap import TimelineHeatmap
from app.shared.database import get_db

router = APIRouter(prefix='/api', tags=['timeline-heatmap'])


@router.get('/archives/{archive_id}/folders/{folder_id}/timeline-heatmap')
async def get_timeline_heatmap(
	archive_id: uuid.UUID,
	folder_id: uuid.UUID,
	y_dimension: str = Query('organisations', pattern='^(organisations|persons|locations|misc|topics)$'),
	range_min: int | None = None,
	range_max: int | None = None,
	db: AsyncSession = Depends(get_db),
):
	result = await TimelineHeatmap(db).execute(archive_id, folder_id, y_dimension, range_min, range_max)
	if result is None:
		raise HTTPException(status_code=404, detail='Folder not found')
	return result
