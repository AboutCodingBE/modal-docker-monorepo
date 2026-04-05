import os
import uuid
from datetime import datetime, timezone

import httpx

from app.config import settings


class FolderAnalysis:
    """Retrieves folder contents from the local agent and returns a flat list of
    file and directory metadata entries that match the 'files' table schema.

    Entries are sorted parents-first so that parent_id can be resolved
    sequentially in FileRepository without extra lookups.
    """

    async def analyze(self, archive_id: uuid.UUID, folder_path: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.agent_url}/files",
                params={"path": folder_path},
                timeout=300.0,
            )
            resp.raise_for_status()
            data = resp.json()

        discovered_at = datetime.now(timezone.utc)
        entries = []

        for f in data["files"]:
            is_directory = f.get("is_directory", False)
            modified_at = (
                datetime.fromtimestamp(f["modified"], tz=timezone.utc)
                if f.get("modified")
                else None
            )

            if is_directory:
                entry = {
                    "archive_id": archive_id,
                    "_parent_path": os.path.dirname(f["absolute_path"]),
                    "name": f["name"],
                    "full_path": f["absolute_path"],
                    "relative_path": f["relative_path"],
                    "is_directory": True,
                    "extension": None,
                    "size_bytes": None,
                    "sha256_hash": None,
                    "created_at": None,
                    "modified_at": modified_at,
                    "discovered_at": discovered_at,
                }
            else:
                _, ext = os.path.splitext(f["name"])
                entry = {
                    "archive_id": archive_id,
                    "_parent_path": os.path.dirname(f["absolute_path"]),
                    "name": f["name"],
                    "full_path": f["absolute_path"],
                    "relative_path": f["relative_path"],
                    "is_directory": False,
                    "extension": ext.lower() if ext else None,
                    "size_bytes": f.get("size_bytes"),
                    "sha256_hash": None,
                    "created_at": None,
                    "modified_at": modified_at,
                    "discovered_at": discovered_at,
                }

            entries.append(entry)

        return entries
