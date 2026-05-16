#!/usr/bin/env python3
"""
CLI entry point called by the Tauri Rust command.

Usage:  python3 main.py

Exit 0 + JSON array on stdout → success
Exit 1 + error on stdout      → failure
"""
import logging
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared.logging_config import setup_logging
from get_archive_overview.get_archives import GetArchives

setup_logging()
_logger = logging.getLogger("app")


def main() -> None:
    try:
        archives = GetArchives().execute()
        print(json.dumps(archives, default=str))
    except Exception as e:
        _logger.error(f"Onverwachte fout: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
