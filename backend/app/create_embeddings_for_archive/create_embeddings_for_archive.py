import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.config import settings
from app.create_embeddings_for_archive.embedding_engine import chunk_text
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.shared.file_repository import FileRepository
from app.shared.logging_config import log_context
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
        # WARNING (niet INFO): embedding_max_chunks_per_file kan momenteel data laten
        # vallen (default 1, zie app/config.py) — dit moet opvallen in de logs.
        _logger.warning(
            f"{log_context(archive_id)}Embedding-analyse gestart met "
            f"model={settings.embedding_model}, dimension={settings.embedding_dimension}, "
            f"chunk_size={settings.embedding_chunk_size}, "
            f"max_chunks_per_file={settings.embedding_max_chunks_per_file}"
        )

        try:
            # ── Phase 0: start task, bestandslijst ophalen, te kleine bestanden filteren ──
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)
                processing_settings = await ProcessingSettingsRepository(session).get()

                file_repo = FileRepository(session)
                files = await file_repo.get_files_with_tika_content(archive_id)

                if processing_settings.minimum_text_length > 0:
                    files = [
                        f for f in files
                        if len(f["content"] or "") >= processing_settings.minimum_text_length
                    ]

                await task_tracker.update_total_files(session, task_id, len(files))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # ── File embedding loop ────────────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # TODO (stap 9/10): al-embedde bestanden overslaan via
                # EmbeddingRepository(session).exists(file_id) — nu altijd False.
                already_processed = False
                if already_processed:
                    processed += 1
                    continue

                async with self._session_factory() as session:
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, file["relative_path"]
                    )
                    await session.commit()

                try:
                    text = file["content"] or ""
                    chunks = chunk_text(text, settings.embedding_chunk_size)

                    if settings.embedding_max_chunks_per_file is not None:
                        chunks = chunks[: settings.embedding_max_chunks_per_file]

                    embedded_chunks: list[tuple[int, str, list[float] | None]] = []
                    for chunk_index, chunk in enumerate(chunks):
                        # TODO (stap 5/6): vervangen door de echte aanroep naar
                        # app.shared.ollama_client.embed(settings.embedding_model, chunk)
                        embedding: list[float] | None = None  # placeholder
                        embedded_chunks.append((chunk_index, chunk, embedding))

                    # TODO (stap 8/9): vervangen door EmbeddingRepository(session).persist(
                    #     file_id, embedded_chunks
                    # )

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
