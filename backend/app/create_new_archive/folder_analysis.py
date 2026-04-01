import os
from datetime import datetime, timezone


def _fs_timestamp(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class FolderAnalysis:
    """Walks a folder tree and returns a flat list of file/directory metadata entries.

    Each entry is a dict that matches the 'files' table schema.
    Entries are ordered parent-first so FileRepository can resolve parent_ids
    in a single pass.  A '_parent_path' key carries the parent's full path;
    FileRepository replaces it with the real parent_id after assigning IDs.
    """

    def analyze(self, archive_id: int, folder_path: str) -> list[dict]:
        entries: list[dict] = []
        discovered_at = datetime.now(timezone.utc).isoformat()

        for root, dirs, files in os.walk(folder_path):
            dirs.sort()  # deterministic order

            rel_path = os.path.relpath(root, folder_path)
            rel_path = "" if rel_path == "." else rel_path.replace(os.sep, "/")

            parent_full = os.path.dirname(root)

            # Directory entry
            entries.append({
                "archive_id": archive_id,
                "_parent_path": parent_full if root != folder_path else None,
                "name": os.path.basename(root) or root,
                "full_path": root,
                "relative_path": rel_path,
                "is_directory": True,
                "extension": None,
                "size_bytes": None,
                "sha256_hash": None,
                "created_at": _fs_timestamp(self._ctime(root)),
                "modified_at": _fs_timestamp(self._mtime(root)),
                "discovered_at": discovered_at,
            })

            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                try:
                    if not os.path.isfile(file_path):
                        continue
                    stat = os.stat(file_path)
                    _, ext = os.path.splitext(filename)
                    file_rel = os.path.join(rel_path, filename).replace(os.sep, "/")
                    entries.append({
                        "archive_id": archive_id,
                        "_parent_path": root,
                        "name": filename,
                        "full_path": file_path,
                        "relative_path": file_rel,
                        "is_directory": False,
                        "extension": ext.lower() if ext else None,
                        "size_bytes": stat.st_size,
                        "sha256_hash": None,
                        "created_at": _fs_timestamp(stat.st_ctime),
                        "modified_at": _fs_timestamp(stat.st_mtime),
                        "discovered_at": discovered_at,
                    })
                except (PermissionError, OSError):
                    continue

        return entries

    def _ctime(self, path: str) -> float | None:
        try:
            return os.stat(path).st_ctime
        except OSError:
            return None

    def _mtime(self, path: str) -> float | None:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return None
