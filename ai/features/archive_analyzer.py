import os


class ArchiveAnalyzer:
    def __init__(self, storage):
        self._storage = storage

    def analyze(self, archive_id: str, folder_path: str):
        total_files = 0
        file_types = {}
        folder_structure = {}

        try:
            for root, dirs, files in os.walk(folder_path):
                rel_path = os.path.relpath(root, folder_path)
                if rel_path == ".":
                    rel_path = "/"
                else:
                    rel_path = "/" + rel_path.replace(os.sep, "/")

                files_in_folder = 0
                for filename in files:
                    file_path = os.path.join(root, filename)
                    try:
                        if os.path.isfile(file_path):
                            total_files += 1
                            files_in_folder += 1
                            _, ext = os.path.splitext(filename)
                            ext = ext.lower() if ext else "no_extension"
                            file_types[ext] = file_types.get(ext, 0) + 1
                    except (PermissionError, OSError):
                        continue

                folder_structure[rel_path] = {
                    "files_count": files_in_folder,
                    "subfolders": sorted(dirs),
                }
        except (PermissionError, OSError):
            pass

        self._storage.store_analysis(archive_id, {
            "total_files": total_files,
            "file_types": file_types,
            "folder_structure": folder_structure,
        })
        self._storage.update_status(archive_id, "ready")
