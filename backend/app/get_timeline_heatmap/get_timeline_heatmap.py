import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_timeline_heatmap.repository import TimelineHeatmapRepository

HeatmapDimension = Literal['organisations', 'persons', 'locations', 'misc', 'topics']


class TimelineHeatmap:
	def __init__(self, session: AsyncSession):
		self.repo = TimelineHeatmapRepository(session)

	async def execute(self, archive_id: uuid.UUID, folder_id: uuid.UUID, dimension: HeatmapDimension, range_min: int | None = None, range_max: int | None = None) -> dict | None:
		folder = await self.repo.get_folder(archive_id, folder_id)
		if folder is None:
			return None
		file_ids = await self.repo.get_file_ids(archive_id, folder_id)
		years = await self.repo.get_years(file_ids)
		if not years:
			return self._empty(folder_id, folder.name, dimension)
		available_min, available_max = min(years), max(years)
		if range_min is None or range_max is None:
			files_by_year = await self.repo.get_files_by_year(file_ids)
			center = max(years, key=lambda year: len(files_by_year.get(year, [])))
			range_min, range_max = center - 5, center + 5
		values_by_file = await self.repo.get_values(file_ids, dimension)
		counts: dict[str, int] = {}
		display_keys: dict[str, str] = {}
		for values in values_by_file.values():
			for value in set(values):
				key = value.casefold()
				display_keys.setdefault(key, value)
				display_value = display_keys[key]
				counts[display_value] = counts.get(display_value, 0) + 1
		y_values = sorted(counts, key=lambda value: (-counts[value], value.casefold()))
		files_by_year = await self.repo.get_files_by_year(file_ids)
		cells = []
		for year in range(range_min, range_max + 1):
			for value in y_values:
				normalized_value = value.casefold()
				count = sum(normalized_value in {item.casefold() for item in values_by_file.get(file_id, [])} for file_id in files_by_year.get(year, []))
				cells.append({'year': year, 'y_value': value, 'count': count})
		return {'folder_id': str(folder_id), 'folder_name': folder.name, 'y_dimension': dimension, 'years': list(range(range_min, range_max + 1)), 'available_range': [available_min, available_max], 'y_values': y_values, 'y_value_counts': counts, 'default_range': [range_min, range_max], 'cells': cells}

	@staticmethod
	def _empty(folder_id: uuid.UUID, folder_name: str, dimension: str) -> dict:
		return {'folder_id': str(folder_id), 'folder_name': folder_name, 'y_dimension': dimension, 'years': [], 'available_range': [None, None], 'y_values': [], 'y_value_counts': {}, 'default_range': [None, None], 'cells': []}
