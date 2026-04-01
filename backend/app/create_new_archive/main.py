#!/usr/bin/env python3
"""
CLI entry point called by the Tauri Rust command.

Usage:  python3 main.py <archive_name> <folder_path>

Exit 0 + empty stdout  → success
Exit 1 + message on stdout → business-logic or unexpected error
"""
import sys
import os

# Ensure the python/ directory is on the path so shared and sibling packages resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from create_new_archive.create_archive import CreateArchive


def main() -> None:
    if len(sys.argv) != 3:
        print("Gebruik: main.py <naam> <pad>")
        sys.exit(1)

    name = sys.argv[1]
    path = sys.argv[2]

    try:
        error = CreateArchive().execute(name, path)
    except Exception as e:
        print(f"Onverwachte fout: {e}")
        sys.exit(1)

    if error is not None:
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
