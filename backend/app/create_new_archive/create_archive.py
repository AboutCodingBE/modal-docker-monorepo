from sqlalchemy.ext.asyncio import AsyncSession

from app.create_new_archive.archive_repository import ArchiveRepository
from app.create_new_archive.file_repository import FileRepository
from app.create_new_archive.folder_analysis import FolderAnalysis


class CreateArchive:
    """Flow controller for creating a new archive and running the initial folder analysis."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._folder_analysis = FolderAnalysis()

    async def execute(self, name: str, path: str) -> None | str:
        """
        Validates inputs, persists the archive, then runs and persists the folder analysis.

        Returns None on success, or an error message string on failure.
        """
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
            entries = self._folder_analysis.analyze(archive.id, path)
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
        return None
