import uuid
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, Ner, TikaAnalysis, TopicDetection


class TimelineHeatmapRepository:
	def __init__(self, session: AsyncSession):
		self._session = session

	async def get_folder(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> File | None:
		result = await self._session.execute(select(File).where(
			File.id == folder_id,
			File.archive_id == archive_id,
			File.is_directory.is_(True),
		))
		return result.scalar_one_or_none()

	async def get_file_ids(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> list[uuid.UUID]:
		folder_path = await self._session.scalar(select(File.full_path).where(
			File.id == folder_id, File.archive_id == archive_id,
		))
		if folder_path is None:
			return []
		result = await self._session.execute(select(File.id).where(
			File.archive_id == archive_id,
			File.is_directory.is_(False),
			File.full_path.like(f'{folder_path}%'),
		))
		return list(result.scalars())

	async def get_files_by_year(self, file_ids: list[uuid.UUID]) -> dict[int, list[uuid.UUID]]:
		result = await self._session.execute(
			select(extract('year', TikaAnalysis.content_created_at), File.id)
			.select_from(File)
			.join(TikaAnalysis, TikaAnalysis.file_id == File.id)
			.where(File.id.in_(file_ids), TikaAnalysis.content_created_at.is_not(None))
		)
		grouped: dict[int, list[uuid.UUID]] = {}
		for year, file_id in result.all():
			grouped.setdefault(int(year), []).append(file_id)
		return grouped

	async def get_values(self, file_ids: list[uuid.UUID], dimension: str) -> dict[uuid.UUID, list[str]]:
		if dimension == 'topics':
			query = select(TopicDetection.file_id, TopicDetection.topics).where(TopicDetection.file_id.in_(file_ids))
		else:
			query = select(Ner.file_id, getattr(Ner, dimension)).where(Ner.file_id.in_(file_ids))
		result = await self._session.execute(query)
		values: dict[uuid.UUID, list[str]] = {}
		for file_id, raw_values in result.all():
			values[file_id] = [item.get('topic' if dimension == 'topics' else 'entity') for item in (raw_values or []) if item.get('topic' if dimension == 'topics' else 'entity')]
		return values

	async def get_years(self, file_ids: list[uuid.UUID]) -> list[int]:
		result = await self._session.execute(
			select(func.distinct(extract('year', TikaAnalysis.content_created_at)))
			.select_from(File)
			.join(TikaAnalysis, TikaAnalysis.file_id == File.id)
			.where(File.id.in_(file_ids), TikaAnalysis.content_created_at.is_not(None))
			.order_by(extract('year', TikaAnalysis.content_created_at))
		)
		return [int(year) for year, in result.all()]
