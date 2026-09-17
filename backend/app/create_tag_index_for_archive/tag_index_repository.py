import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TagIndex


class TagIndexRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, analysis_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Returns True if this (analysis, file) is already tag-indexed (resumability check).
           query: SELECT id FROM tag_index WHERE analysis_id = :analysis_id AND file_id = :file_id LIMIT 1
        """
        result = await self._session.execute(
            select(TagIndex.id)
            .where(TagIndex.analysis_id == analysis_id, TagIndex.file_id == file_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def persist(
        self,
        archive_id: uuid.UUID,
        analysis_id: uuid.UUID,
        file_id: uuid.UUID,
        entries: list[tuple[str, str | None, str, int]],
    ) -> None:
        """Slaat alle tags van één (analysis, file) op als aparte TagIndex-rijen.

        entries: lijst van (source, category, value, count).

        Gebruikt ON CONFLICT DO NOTHING op de UniqueConstraint
        (file_id, source, category, value) — een dubbele tag voor hetzelfde bestand
        wordt stilzwijgend genegeerd i.p.v. te falen op de constraint. Dat is nodig
        omdat één bestand meerdere keren dezelfde entiteit/topic kan opleveren
        (bv. via een herstart na een gedeeltelijke failure).
        """
        if not entries:
            return

        stmt = insert(TagIndex).values([
            {
                "archive_id": archive_id,
                "analysis_id": analysis_id,
                "file_id": file_id,
                "source": source,
                "category": category,
                "value": value,
                "count": count,
            }
            for source, category, value, count in entries
        ]).on_conflict_do_nothing(constraint="uq_tag_index_file_source_category_value")

        await self._session.execute(stmt)
        await self._session.flush()

    async def search(self, archive_id: uuid.UUID, prefix: str, top_n: int) -> list[dict]:
        """Prefix-zoekopdracht binnen 1 archief — voor een typeahead-zoekbalk.

        Geeft per match de tag zelf (waarde/source/categorie) terug, samen met het
        bestand of de map waarin die tag voorkomt (is_directory onderscheidt beide —
        tag_index bevat ook folder-aggregaten, zie CreateTagIndexForArchive).
        """
        stmt = (
            select(
                TagIndex.value,
                TagIndex.source,
                TagIndex.category,
                File.id.label("file_id"),
                File.name.label("file_name"),
                File.relative_path,
                File.is_directory,
            )
            .join(File, File.id == TagIndex.file_id)
            .where(TagIndex.archive_id == archive_id, TagIndex.value.ilike(f"{prefix}%"))
            .order_by(TagIndex.value)
            .limit(top_n)
        )
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]
