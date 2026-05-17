import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.create_ner_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_ner_for_archive.file_repository import FileRepository
from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository

_MAX_CONSECUTIVE_FAILURES = 5


class CreateNerForArchive:
    """Flow controller for spaCy NER analysis of all files in an archive."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._file_repo = FileRepository(session)
        self._ner_repo = NerRepository(session)
        self._analysis_repo = ArchiveAnalysisRepository(session)

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
    ) -> None:
        await task_tracker.start_task(self._session, task_id)
        await self._session.commit()

        try:
            files = await self._file_repo.get_files_with_tika_content(archive_id)

            await task_tracker.update_total_files(self._session, task_id, len(files))
            await self._session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            for file in files:
                file_id: uuid.UUID = file["id"]

                # Skip already-processed files (allows resuming interrupted runs)
                if await self._ner_repo.exists(archive_analysis_id, file_id):
                    processed += 1
                    continue

                await task_tracker.update_progress(
                    self._session, task_id, processed, failed_count, file["relative_path"]
                )
                await self._session.commit()

                try:
                    text = file["content"] or ""
                    # run_ner is synchronous (spaCy); offload to a thread to avoid blocking the event loop
                    ner_result = await asyncio.to_thread(run_ner, text, model)
                    await self._ner_repo.persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, ner_result
                    )
                    processed += 1
                    consecutive_failures = 0
                except Exception as e:
                    print(f"Failed to run NER on file {file['name']}: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        print("Repeated failures — NER processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return

                await self._session.commit()

            await task_tracker.update_progress(self._session, task_id, processed, failed_count, None)
            await task_tracker.complete_task(self._session, task_id)
            await self._analysis_repo.update_status(archive_analysis_id, "COMPLETED")
            await self._session.commit()
            print(f"NER complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            print(f"NER task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_id: uuid.UUID) -> None:
        await task_tracker.fail_task(self._session, task_id)
        await self._analysis_repo.update_status(archive_analysis_id, "FAILED")
        await self._session.commit()
