import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import (
    AnalysisType,
    ArchiveAnalysis,
    ArchiveAnalysisStatus,
    File,
    GenericType,
    Ner,
    Summary,
    TikaAnalysis,
    TopicDetection,
)


def _extract_entities(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["entity"] for item in jsonb_list if "entity" in item]


def _extract_topics(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["topic"] for item in jsonb_list if "topic" in item]


class ExportDataRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_latest_completed_analysis(
        self, archive_id: uuid.UUID, analysis_type: AnalysisType
    ) -> ArchiveAnalysis | None:
        # TODO once bugfix-context-archive-analysis-analyzed-at lands:
        # change .order_by(ArchiveAnalysis.date.desc()) to
        # .order_by(ArchiveAnalysis.analyzed_at.desc()) — this is the only
        # change this file will need at that point.
        result = await self._session.execute(
            select(ArchiveAnalysis)
            .where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.type == analysis_type,
                ArchiveAnalysis.status == ArchiveAnalysisStatus.COMPLETED,
            )
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_summaries(self, analysis_id: uuid.UUID) -> dict[uuid.UUID, Summary]:
        result = await self._session.execute(
            select(Summary).where(Summary.analysis_id == analysis_id)
        )
        return {s.file_id: s for s in result.scalars().all()}

    async def _load_ner(self, analysis_id: uuid.UUID) -> dict[uuid.UUID, Ner]:
        result = await self._session.execute(
            select(Ner).where(Ner.analysis_id == analysis_id)
        )
        return {n.file_id: n for n in result.scalars().all()}

    async def _load_topics(self, analysis_id: uuid.UUID) -> dict[uuid.UUID, TopicDetection]:
        result = await self._session.execute(
            select(TopicDetection).where(TopicDetection.analysis_id == analysis_id)
        )
        return {t.file_id: t for t in result.scalars().all()}

    async def get_export_rows(self, archive_id: uuid.UUID, content_char_limit: int) -> list[dict]:
        # Step 1: resolve the most recent COMPLETED analysis for each type (at most 3 lookups)
        summary_analysis = await self._get_latest_completed_analysis(archive_id, AnalysisType.SUMMARY)
        ner_analysis = await self._get_latest_completed_analysis(archive_id, AnalysisType.NER)
        topic_analysis = await self._get_latest_completed_analysis(archive_id, AnalysisType.TOPIC_DETECTION)

        # Step 2: bulk load results keyed by file_id
        summaries_by_file = await self._load_summaries(summary_analysis.id) if summary_analysis else {}
        ner_by_file = await self._load_ner(ner_analysis.id) if ner_analysis else {}
        topics_by_file = await self._load_topics(topic_analysis.id) if topic_analysis else {}

        # Step 3: load all files/folders with LEFT JOINs to tika and generic_type
        files_result = await self._session.execute(
            select(File, TikaAnalysis, GenericType)
            .outerjoin(TikaAnalysis, TikaAnalysis.file_id == File.id)
            .outerjoin(GenericType, GenericType.file_id == File.id)
            .where(File.archive_id == archive_id)
            .order_by(File.relative_path)
        )

        rows = []
        for file, tika, generic_type in files_result.all():
            summary = summaries_by_file.get(file.id)
            ner = ner_by_file.get(file.id)
            topics = topics_by_file.get(file.id)

            content_excerpt = None
            if tika and tika.content:
                content_excerpt = tika.content[:content_char_limit]

            rows.append({
                "file_id": file.id,
                "parent_id": file.parent_id,
                "relative_path": file.relative_path,
                "name": file.name,
                "is_directory": file.is_directory,
                # file-only fields — None for directories
                "extension": None if file.is_directory else file.extension,
                "size_bytes": None if file.is_directory else file.size_bytes,
                "mime_type": None if file.is_directory else (tika.mime_type if tika else None),
                "language": None if file.is_directory else (tika.language if tika else None),
                "word_count": None if file.is_directory else (tika.word_count if tika else None),
                "author": None if file.is_directory else (tika.author if tika else None),
                "content_excerpt": None if file.is_directory else content_excerpt,
                "generic_type": None if file.is_directory else (generic_type.generic_type if generic_type else None),
                # summary — model/analyzed_at constant for all rows when analysis ran
                "summary_result": summary.result if summary else None,
                "summary_model": summary_analysis.model if summary_analysis else None,
                "summary_analyzed_at": summary_analysis.date.isoformat() if summary_analysis else None,
                # ner
                "ner_persons": _extract_entities(ner.persons) if ner else [],
                "ner_locations": _extract_entities(ner.locations) if ner else [],
                "ner_organisations": _extract_entities(ner.organisations) if ner else [],
                "ner_misc": _extract_entities(ner.misc) if ner else [],
                "ner_model": ner_analysis.model if ner_analysis else None,
                "ner_analyzed_at": ner_analysis.date.isoformat() if ner_analysis else None,
                # topics
                "topics": _extract_topics(topics.topics) if topics else [],
                "topics_model": topic_analysis.model if topic_analysis else None,
                "topics_analyzed_at": topic_analysis.date.isoformat() if topic_analysis else None,
            })

        return rows
