import logging
import uuid
import json

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.config import settings
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.shared.analysis_engine_registry import classify_llm_engine, get_llm_provider
from app.shared.llm.provider import LlmProviderUnavailableError
from app.create_topic_detection_for_archive.topic_detection_repository import TopicDetectionRepository
from app.shared.file_repository import FileRepository
from app.shared.logging_config import log_context
from app.shared.processing_settings_repository import ProcessingSettingsRepository

_logger = logging.getLogger("app.topic")

_MAX_CONSECUTIVE_FAILURES = 5


def _topic_prompt(text: str) -> str:
    """Prompt forcing the model to adhere to a specific JSON format."""
    return (
        "Je bent een AI die metadata extraheert uit documenten. Analyseer de onderstaande tekst en identificeer de belangrijkste overkoepelende onderwerpen (topics/trefwoorden).\n\n"
        "RECHTLIJNEN:\n"
        "- Geef de resultaten terug in het Nederlands.\n"
        "- Genereer maximaal 5 topics. Minder mag ook, of een lege lijst [] als de tekst geen duidelijke onderwerpen bevat.\n"
        "- Genereer GEEN inleiding, GEEN verklaring en GEEN markdown-codeblocks (zoals ```json).\n\n"
        "Je MOET antwoorden in dit exacte JSON-formaat:\n"
        '{\n  "topics": ["topic1", "topic2"]\n}\n\n'
        f"Tekst om te analyseren:\n\n{text}"
    )


class CreateTopicDetectionForArchive:
    """Flow controller for AI topic generation of an archive (files only).

    Accepts a session_factory rather than a single session so that each unit of
    DB work gets its own short-lived connection. The connection is released
    before every Ollama call, preventing pool exhaustion during long analyses.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
    ) -> None:
        try:
            # ── Phase 0: start task and fetch file + folder list ──────────────
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)
                file_repo = FileRepository(session)
                files = await file_repo.get_files_with_tika_content(archive_id)
                folders = await file_repo.get_all_folders(archive_id)
                await task_tracker.update_total_files(session, task_id, len(files) + len(folders))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            provider = get_llm_provider(classify_llm_engine(model))

            async with self._session_factory() as session:
                processing_settings = await ProcessingSettingsRepository(session).get()

            # ── Phase 1: file topic extraction ──────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check if topics have already been generated for this file
                already_processed = False
                async with self._session_factory() as session:
                    already_processed = await TopicDetectionRepository(session).exists(archive_analysis_id, file_id)
                    if not already_processed:
                        await task_tracker.update_progress(
                            session, task_id, processed, failed_count, file["relative_path"]
                        )
                        await session.commit()
                if already_processed:
                    processed += 1
                    continue

                # No DB connection held during the LLM HTTP call.
                try:
                    text = (file["content"] or "")[:processing_settings.topic_char_limit]
                    raw_response = await provider.generate(model, _topic_prompt(text), format="json")
                    response_data = json.loads(raw_response)
                    topics_list = response_data.get("topics", [])
                    validated_topics = topics_list[:5]

                except json.JSONDecodeError:
                    _logger.warning(f"{log_context(archive_id, file['name'])} Invalid JSON returned by LLM. Falling back to empty list.")
                    validated_topics = []

                except LlmProviderUnavailableError:
                    _logger.error(f"{log_context(archive_id)}LLM provider unavailable — stopping topic detection")
                    await self._fail(task_id, archive_analysis_id)
                    return
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file['name'])}Failed to detect topics from file: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                # Write the validated result to the database
                async with self._session_factory() as session:
                    await TopicDetectionRepository(session).persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, validated_topics
                    )
                    await session.commit()

                processed += 1
                consecutive_failures = 0

            # ── Phase 2: folder aggregation (bottom-up) ───────────────────────
            folders_processed = 0
            for folder in folders:
                folder_id: uuid.UUID = folder["id"]

                async with self._session_factory() as session:
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, folder["relative_path"]
                    )
                    await session.commit()

                try:
                    skip_folder = False
                    async with self._session_factory() as session:
                        topics = await TopicDetectionRepository(session).get_topics_for_folder(
                            archive_analysis_id, folder_id, settings.topic_folder_top_n
                        )
                        if not topics:
                            skip_folder = True
                        else:
                            await TopicDetectionRepository(session).persist_folder(
                                archive_analysis_id, archive_id, folder["parent_id"], folder_id, topics
                            )
                            await session.commit()
                    if skip_folder:
                        processed += 1
                        continue
                except Exception as e:
                    _logger.error(
                        f"{log_context(archive_id, folder['name'])}"
                        f"Failed to aggregate topics for folder: {e}"
                    )
                    failed_count += 1
                    processed += 1
                    continue

                folders_processed += 1
                processed += 1

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(
                f"{log_context(archive_id)}Topic detection complete. "
                f"Files processed: {processed - folders_processed}, "
                f"folders aggregated: {folders_processed}, "
                f"failed: {failed_count}"
            )

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Topic detection task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()