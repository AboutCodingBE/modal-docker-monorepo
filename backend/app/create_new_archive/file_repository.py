import uuid

from sqlalchemy.orm import Session

from shared.models import File

BATCH_SIZE = 500


class FileRepository:
    """Persists file/directory entries in batches of 500.

    Resolves '_parent_path' references to real parent_ids as entries are saved,
    relying on the parent-first ordering guaranteed by FolderAnalysis.
    UUIDs are generated in Python so no flush-per-row is needed to retrieve IDs.
    """

    def __init__(self, session: Session):
        self._session = session

    def persist_all(self, entries: list[dict]) -> None:
        path_to_id: dict[str, uuid.UUID] = {}

        for batch_start in range(0, len(entries), BATCH_SIZE):
            batch = entries[batch_start: batch_start + BATCH_SIZE]
            self._persist_batch(batch, path_to_id)

    def _persist_batch(self, batch: list[dict], path_to_id: dict[str, uuid.UUID]) -> None:
        for entry in batch:
            parent_path = entry.pop("_parent_path", None)
            parent_id = path_to_id.get(parent_path) if parent_path else None

            file = File(id=uuid.uuid4(), **entry, parent_id=parent_id)
            self._session.add(file)
            path_to_id[file.full_path] = file.id

        self._session.flush()
