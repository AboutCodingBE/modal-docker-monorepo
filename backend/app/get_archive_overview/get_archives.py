from get_archive_overview.archive_repository import ArchiveRepository


class GetArchives:
    """Flow controlling function. Delegates to ArchiveRepository."""

    def __init__(self):
        self._repo = ArchiveRepository()

    def execute(self) -> list[dict]:
        return self._repo.get_all()
