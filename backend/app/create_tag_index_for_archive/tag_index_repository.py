import uuid
from typing import Literal

from sqlalchemy import func, select
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

    async def search(
        self,
        archive_id: uuid.UUID,
        prefix: str,
        top_n: int,
        source: str | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """Prefix-zoekopdracht binnen 1 archief — voor een typeahead-zoekbalk.

        Optioneel te beperken tot een source ("ner" of "topic_detection") en/of
        een category ("persons", "locations", ...) — zo kan autocomplete apart
        zoeken op entiteitstype of enkel op topics.

        Gebruikt unaccent zodat accenten in het zoekprefix of de opgeslagen waarde
        geen invloed hebben op de match (bv. "Gent" matcht "Gënt").
        """
        conditions = [
            TagIndex.archive_id == archive_id,
            func.immutable_unaccent(TagIndex.value).ilike(
                func.concat(func.immutable_unaccent(prefix), "%")
            ),
        ]
        if source is not None:
            conditions.append(TagIndex.source == source)
        if category is not None:
            conditions.append(TagIndex.category == category)

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
            .where(*conditions)
            .distinct(func.lower(TagIndex.value))
            .order_by(func.lower(TagIndex.value), TagIndex.value)
            .limit(top_n)
        )
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def search_by_tags(
        self,
        archive_id: uuid.UUID,
        values: list[str],
        top_n: int,
        match: Literal["any", "all"] = "any",
    ) -> list[dict]:
        """Multi-tag filter — voor een filterpaneel waar de gebruiker al concrete tags
        heeft aangeklikt (exacte match, geen ILIKE-prefix zoals search()).

        match="any" (OR): bestanden met minstens 1 van de opgegeven tags.
        match="all" (AND): enkel bestanden met alle opgegeven tags tegelijk.

        Geeft, net als search(), 1 rij per (tag, bestand)-match terug.

        bv.: await repo.search_by_tags(archive_id, values=["Jan Janssens", "Gent"], top_n=25, match="all")
        """

        if not values:
            return []

        # value IN (values) = OR-selectie op rij-niveau: elke rij met 1 van de
        # gevraagde waarden matcht. Bij match="any" is dit de volledige query.
        lowered = [v.lower() for v in values]
        filters = [TagIndex.archive_id == archive_id, func.lower(TagIndex.value).in_(lowered)]

        if match == "all":
            # AND op bestand-niveau:
            # formaat tabel: 1 rij = 1 (tag, file), we filteren dus eerst alle rijen die aan 1
            # van de values voldoet. Vervolgens doen we groupby file_id en moeten we als we tellen
            # altijd op len(values) uitkomen anders matcht een file niet met ALLE tags.
            #   func.distinct(value)        -> DISTINCT value, binnen die groep
            #   func.count(...)             -> COUNT(...) daarvan
            #   HAVING count(...) == len(values)  -> telt
            qualifying_files = (
                select(TagIndex.file_id)
                .where(*filters)  # nog enkel de 2 basisvoorwaarden hierboven
                .group_by(TagIndex.file_id)
                .having(func.count(func.distinct(func.lower(TagIndex.value))) == len(set(lowered)))
            )
            # qualifying_files wordt hier zelf niet uitgevoerd — het wordt als
            # subquery ingeplakt in een 3de filter: "file_id moet in dat lijstje zitten".
            filters.append(TagIndex.file_id.in_(qualifying_files))

        # stmt: haal de tag + bestandsinfo op voor elke tag_index-rij die aan alle filters voldoet
        # (2 filters bij "any", 3 bij "all"  
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
            .where(*filters)  # combineert filters met AND (WHERE a AND b [AND c])
            .order_by(TagIndex.value)
            .limit(top_n)
        )
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def get_all_tags(self, archive_id: uuid.UUID, category: str | None = None) -> list[dict]:
        """Alle unieke tags in dit archief, optioneel gefilterd op category.

        Geen category -> alle tags ongeacht categorie. In tegenstelling tot search()/
        search_by_tags() geen file_id/bestandsinfo in het resultaat: dit is bewust
        gededupliceerd over bestanden heen (DISTINCT) — bedoeld om een filterpaneel
        te vullen met de beschikbare tag-opties, niet om per bestand te tonen.

        LET OP: de DISTINCT werkt op (source, category, value) samen, niet op value
        alleen. Dezelfde tekst kan dus 2x in het resultaat staan als ze in meerdere
        (source, category)-combinaties voorkomt — bv. "Gent" als NER-locatie ÉN als
        LLM-topic. Dat is bewust: met category=None getoond, is dat 2 apart aanklikbare
        filter-opties, geen echte duplicaat. Wil een aanroeper toch een platte lijst van
        unieke tag-teksten (zonder categorie-context), dan dedupliceert die zelf verder,
        bv. {r["value"] for r in resultaten}.
        """
        stmt = select(TagIndex.source, TagIndex.category, TagIndex.value).distinct().where(
            TagIndex.archive_id == archive_id
        )
        if category is not None:
            stmt = stmt.where(TagIndex.category == category)
        stmt = stmt.order_by(TagIndex.value)

        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]
