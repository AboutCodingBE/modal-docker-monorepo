import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.create_new_archive.archive_repository import ArchiveRepository
from app.create_new_archive.file_repository import FileRepository
from app.create_new_archive.folder_analysis import FolderAnalysis
from app.shared.models import Archive
from app.shared.database import _session_factory
from app.analysis import task_tracker
from app.perform_tika_analysis.perform_tika_analysis import PerformTikaAnalysis


class CreateArchive:
    """Flow controller for creating a new archive and running the initial folder analysis."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._folder_analysis = FolderAnalysis()

    async def execute(self, name: str, path: str) -> tuple[Archive, uuid.UUID] | str:
        if not name or not name.strip():
            return "Archiefnaam mag niet leeg zijn."
        if not path or not path.strip():
            return "Mappad mag niet leeg zijn."

        name = name.strip()
        path = path.strip()

        archive_repo = ArchiveRepository(self._session)
        file_repo = FileRepository(self._session)

        archive = await archive_repo.persist(name, path)

        try:
            entries = await self._folder_analysis.analyze(archive.id, path)
        except Exception as e:
            await archive_repo.update_status(archive, "failed", error_message=str(e))
            return f"Fout bij analyseren map: {e}"

        try:
            await file_repo.persist_all(entries)
        except Exception as e:
            await archive_repo.update_status(archive, "failed", error_message=str(e))
            return f"Fout bij opslaan bestanden: {e}"

        file_count = sum(1 for e in entries if not e.get("is_directory", True))
        directory_count = sum(1 for e in entries if e.get("is_directory", False))
        total_size = sum(e.get("size_bytes") or 0 for e in entries)

        await archive_repo.update_statistics(archive, file_count, directory_count, total_size)

        task = await task_tracker.create_task(self._session, archive.id, file_count)

        asyncio.create_task(_run_tika(archive.id, task.id))

        return archive, task.id


async def _run_tika(archive_id: uuid.UUID, task_id: uuid.UUID) -> None:
    async with _session_factory() as session:
        try:
            analyzer = PerformTikaAnalysis(session)
            await analyzer.execute(archive_id, task_id)
        except Exception as e:
            print(f"Background Tika task failed: {e}")
            try:
                await task_tracker.fail_task(session, task_id)
                await session.commit()
            except Exception:
                pass
