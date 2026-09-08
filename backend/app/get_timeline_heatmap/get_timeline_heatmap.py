import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_timeline_heatmap.repository import TimelineHeatmapRepository

type HeatmapDimension = Literal['organisations', 'persons', 'locations', 'misc', 'topics']
type ItemScope = Literal['files', 'folders', 'both']


class TimelineHeatmap:
    def __init__(self, session: AsyncSession):
        self._repo = TimelineHeatmapRepository(session)

    async def execute(
        self,
        archive_id: uuid.UUID,
        folder_id: uuid.UUID,
        y_dimension: HeatmapDimension,
        scope: ItemScope = 'files',
        range_min: int | None = None,
        range_max: int | None = None,
    ) -> dict | None:
        """Execute timeline heatmap query.
        
        Args:
            archive_id: Archive ID
            folder_id: Folder ID
            y_dimension: 'organisations', 'persons', 'locations', 'misc', or 'topics'
            scope: 'files', 'folders', or 'both'
            range_min: Optional min year for filtering (if not provided, calculated from data)
            range_max: Optional max year for filtering (if not provided, calculated from data)
            
        Returns: dict with timeline heatmap data or None if folder not found
        """
        # Verify folder exists
        folder = await self._repo.get_folder(archive_id, folder_id)
        if folder is None:
            return None

        # Get files based on scope
        include_folders = scope in ('folders', 'both')
        file_records = await self._repo.get_files_in_folder(archive_id, folder_id, include_folders)
        
        if not file_records:
            return self._empty_response(folder_id, folder.name, y_dimension, scope)

        # Filter by scope type
        if scope == 'files':
            file_ids = [fid for fid, _, is_dir in file_records if not is_dir]
        elif scope == 'folders':
            file_ids = [fid for fid, _, is_dir in file_records if is_dir]
        else:  # both
            file_ids = [fid for fid, _, _ in file_records]

        if not file_ids:
            return self._empty_response(folder_id, folder.name, y_dimension, scope)

        # Get years with data
        all_years = await self._repo.get_years_with_data(file_ids)
        if not all_years:
            return self._empty_response(folder_id, folder.name, y_dimension, scope)

        # Calculate default range if not provided
        files_by_year = await self._repo.get_files_by_year(file_ids)
        year_with_most_data = max(all_years, key=lambda y: len(files_by_year.get(y, [])))
        
        if range_min is None or range_max is None:
            range_min, range_max = self._calculate_default_range(year_with_most_data)

        years_in_range = list(range(range_min, range_max + 1))

        # Get y-values based on dimension
        y_value_counts = await self._get_y_value_counts(file_ids, y_dimension)
        y_values = sorted(y_value_counts)

        # Build heatmap cells
        cells = await self._build_heatmap_cells(
            file_ids, files_by_year, y_dimension, y_values, years_in_range
        )

        return {
            "folder_id": str(folder_id),
            "folder_name": folder.name,
            "y_dimension": y_dimension,
            "scope": scope,
            "years": years_in_range,
            "available_range": [min(all_years), max(all_years)],
            "y_values": y_values,
            "y_value_counts": y_value_counts,
            "year_with_most_data": year_with_most_data,
            "default_range": [range_min, range_max],
            "cells": cells,
        }

    async def _get_y_value_counts(
        self, file_ids: list[uuid.UUID], dimension: HeatmapDimension
    ) -> dict[str, int]:
        """Count every selected dimension value across the folder scope."""
        counts: dict[str, int] = {}

        if dimension == 'topics':
            topics_by_file = await self._repo.get_topics_for_files(file_ids)
            for topics in topics_by_file.values():
                for topic in topics:
                    counts[topic] = counts.get(topic, 0) + 1
        else:
            entities_by_file = await self._repo.get_ner_entities_for_files(file_ids, dimension)
            for entities in entities_by_file.values():
                for entity in entities:
                    counts[entity] = counts.get(entity, 0) + 1

        return counts

    async def _build_heatmap_cells(
        self,
        file_ids: list[uuid.UUID],
        files_by_year: dict[int, list[uuid.UUID]],
        y_dimension: HeatmapDimension,
        y_values: list[str],
        years: list[int],
    ) -> list[dict]:
        """Build heatmap cells with counts."""
        # Get all data we need
        if y_dimension == 'topics':
            topics_by_file = await self._repo.get_topics_for_files(file_ids)
            data_by_file = topics_by_file
        else:
            entities_by_file = await self._repo.get_ner_entities_for_files(file_ids, y_dimension)
            data_by_file = entities_by_file

        # Build cells
        cells = []
        for year in years:
            files_in_year = files_by_year.get(year, [])
            for y_value in y_values:
                # Count how many files in this year contain this y_value
                count = sum(
                    1 for fid in files_in_year
                    if y_value in data_by_file.get(fid, [])
                )
                cells.append({
                    "year": year,
                    "y_value": y_value,
                    "count": count,
                })

        return cells

    @staticmethod
    def _calculate_default_range(center_year: int, window: int = 5) -> tuple[int, int]:
        """Calculate 10-year range centered on center_year.
        
        window: how many years on each side (default 5, giving 10-year window + center)
        """
        range_min = center_year - window
        range_max = center_year + window
        return range_min, range_max

    @staticmethod
    def _empty_response(folder_id: uuid.UUID, folder_name: str, dimension: str, scope: str) -> dict:
        """Return empty heatmap response."""
        return {
            "folder_id": str(folder_id),
            "folder_name": folder_name,
            "y_dimension": dimension,
            "scope": scope,
            "years": [],
            "available_range": [None, None],
            "y_values": [],
            "y_value_counts": {},
            "year_with_most_data": None,
            "default_range": [None, None],
            "cells": [],
        }
