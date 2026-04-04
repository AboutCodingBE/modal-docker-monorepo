import os
import uuid
from datetime import datetime, timezone

import httpx

from app.config import settings


class FolderAnalysis:
    """Retrieves folder contents from the local agent and returns a flat list of
    file metadata entries that match the 'files' table schema.

    The agent is the only component with direct filesystem access; the backend
    always goes through it rather than calling os.walk() directly.
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

        discovered_at = datetime.now(timezone.utc).isoformat()
        entries = []

        for f in data["files"]:
            _, ext = os.path.splitext(f["name"])
            modified_at = (
                datetime.fromtimestamp(f["modified"], tz=timezone.utc).isoformat()
                if f.get("modified")
                else None
            )
            entries.append({
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
            })

        return entries
