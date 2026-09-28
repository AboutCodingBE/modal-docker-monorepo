import logging
import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.create_ner_for_archive.ner_repository import NerRepository
from app.create_tag_index_for_archive.tag_index_engine import extract_ner_tags, extract_topics
from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository
from app.create_topic_detection_for_archive.topic_detection_repository import TopicDetectionRepository
from app.shared.logging_config import log_context

_logger = logging.getLogger("app")

_MAX_CONSECUTIVE_FAILURES = 5


class CreateTagIndexForArchive:
    """Flow controller die tag_index vult vanuit de bestaande Ner- of TopicDetection-
    rijen van één analyse.

    Wordt stil aangeroepen aan het eind van CreateNerForArchive/CreateTopicDetectionForArchive,
    ná hun eigen update_status(..., "COMPLETED") — dit is een nabewerking, geen eigen
    AnalysisTask: puur DB-gebonden (geen LLM/Ollama-call), dus geen aparte voortgangsbalk
    nodig. Fouten hier worden gelogd maar wijzigen de reeds voltooide status van de
    aanroepende analyse niet.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(
        self,
        archive_id: uuid.UUID,
        analysis_id: uuid.UUID,
        source: Literal["ner", "topic_detection"],
    ) -> None:
        """Vult tag_index voor één analyse (één source: "ner" of "topic_detection").

        Stappen:
          1. Haal alle Ner- of TopicDetection-rijen op voor deze analysis_id
             (rows) — zowel bestanden als folder-aggregaten.
          2. Itereer over rows. Per rij: sla ze over als er al een tag_index-rij
             bestaat voor (analysis_id, file_id) — resumability, zelfde patroon
             als CreateNerForArchive/CreateEmbeddingsForArchive.
          3. Voor een nog niet verwerkte rij: haal met tag_index_engine de losse
             tags eruit (extract_ner_tags/extract_topics geven telkens een lijst
             tuples terug, bv. ("persons", "Jan Janssens", 1)) en zet er de
             "source" voorop — dat zijn precies de (source, category, value, count)-
             tuples die TagIndexRepository.persist() verwacht.
          4. Persist die tuples als tag_index-rijen voor dit bestand.
        """
        try:
            async with self._session_factory() as session:
                if source == "ner":
                    rows = await NerRepository(session).get_all_for_analysis(analysis_id)
                else:
                    rows = await TopicDetectionRepository(session).get_all_for_analysis(analysis_id)

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            for row in rows:
                file_id: uuid.UUID = row.file_id

                async with self._session_factory() as session:
                    already_processed = await TagIndexRepository(session).exists(analysis_id, file_id)
                if already_processed:
                    processed += 1
                    continue

                try:
                    if source == "ner":
                        entries = [(source, category, value, count) for category, value, count in extract_ner_tags(row)]
                    else:
                        entries = [(source, None, value, count) for value, count in extract_topics(row)]

                    async with self._session_factory() as session:
                        await TagIndexRepository(session).persist(archive_id, analysis_id, file_id, entries)
                        await session.commit()
                except Exception as e:
                    _logger.error(f"{log_context(archive_id)}Failed to tag-index file {file_id}: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — tag indexing stopped")
                        return
                    continue

                processed += 1
                consecutive_failures = 0

            _logger.info(
                f"{log_context(archive_id)}Tag indexing ({source}) complete. "
                f"Processed: {processed}, failed: {failed_count}"
            )

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Tag indexing task failed unexpectedly: {e}")
