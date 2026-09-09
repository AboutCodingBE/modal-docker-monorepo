import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.config import settings
from app.create_embeddings_for_archive.embedding_engine import chunk_text
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.shared.file_repository import FileRepository
from app.shared.logging_config import log_context
from app.shared.ollama_client import OllamaUnavailableError, embed
from app.shared.processing_settings_repository import ProcessingSettingsRepository

_logger = logging.getLogger("app")

_MAX_CONSECUTIVE_FAILURES = 5


class CreateEmbeddingsForArchive:
    """Flow controller die voor elk bestand in een archief tekst chunkt en embed.

    Zelfde patroon als CreateNerForArchive: een session_factory i.p.v. een losse sessie,
    zodat elke DB-bewerking een kortstondige connectie gebruikt en geen connecties
    vasthoudt tijdens de (mogelijk trage) embedding-aanroep.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> None:
        
        # WARNING: als embedding_max_chunks_per_file niet None is, wordt niet
        # alle tekst van een bestand embed — een deel van de informatie komt dan niet in
        # de vector-database terecht. Dat moet opvallen in de logs.
        _logger.warning(
            f"{log_context(archive_id)}Embedding-analyse gestart met "
            f"model={settings.embedding_model}, dimension={settings.embedding_dimension}, "
            f"chunk_size={settings.embedding_chunk_size}, "
            f"max_chunks_per_file={settings.embedding_max_chunks_per_file}"
        )
        # Voorbeeld _logger.warning: [archive:50cebbe8] Embedding-analyse gestart met
        # model=qwen3-embedding:0.6b, dimension=1024, chunk_size=512, max_chunks_per_file=1

        try:
            # ── Phase 0: start task, bestandslijst ophalen, te kleine bestanden filteren ──
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)

                # DB-backed configuratierij die o.a. minimum_text_length bepaalt 
                processing_settings = await ProcessingSettingsRepository(session).get()

                # We willen itereren over de files, 1 file => N chunks met N in [0, X]    
                file_repo = FileRepository(session)
                files = await file_repo.get_files_with_tika_content(archive_id)

                # Bestanden met te weinig tekst overslaan (minimum_text_length)
                if processing_settings.minimum_text_length > 0:
                    files = [
                        f for f in files
                        if len(f["content"] or "") >= processing_settings.minimum_text_length
                    ]

                # Totaal aantal bestanden instellen voor progress bar
                await task_tracker.update_total_files(session, task_id, len(files))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # ── File embedding loop: creeer een of meerdere embeddings per file ────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check of dit bestand al embed is (resumability) en update de voortgang —
                # zelfde gecombineerde, kortstondige sessie als bij CreateNerForArchive.
                already_processed = False
                async with self._session_factory() as session:
                    already_processed = await EmbeddingRepository(session).exists(file_id)
                    if not already_processed:
                        await task_tracker.update_progress(
                            session, task_id, processed, failed_count, file["relative_path"]
                        )
                        await session.commit()
                if already_processed:
                    processed += 1
                    continue

                # Geen DB-connectie vastgehouden tijdens chunken + de mogelijk trage embed-aanroepen.
                try:
                    # NOOT: kan eigenlijk nooit None zijn
                    file_text = file["content"] or ""

                    chunks = chunk_text(file_text, settings.embedding_chunk_size)

                    # tokenizen is << embedden, dus geen probleem om eerst alle chunks te maken
                    if settings.embedding_max_chunks_per_file is not None:
                        chunks = chunks[: settings.embedding_max_chunks_per_file]

                    embedded_chunks: list[tuple[int, str, list[float]]] = []
                    for chunk_index, chunk in enumerate(chunks):
                        embedding = await embed(settings.embedding_model, chunk)
                        embedded_chunks.append((chunk_index, chunk, embedding))

                    async with self._session_factory() as session:
                        await EmbeddingRepository(session).persist(file_id, embedded_chunks)
                        await session.commit()

                except OllamaUnavailableError:
                    _logger.error(f"{log_context(archive_id)}Ollama unavailable — stopping embedding analysis")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file['name'])}Failed to embed file: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — embedding processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                processed += 1
                consecutive_failures = 0

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(
                f"{log_context(archive_id)}Embedding-analyse voltooid. "
                f"Bestanden verwerkt: {processed}, mislukt: {failed_count}"
            )

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Embedding task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()
