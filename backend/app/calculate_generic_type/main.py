#!/usr/bin/env python3
"""
CLI entry point
Usage:  python3 main.py <archive_uuid>

Exit 0 + empty stdout  → success
Exit 1 + message on stdout → business-logic or unexpected error
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.calculate_generic_type.generic_type_repository import GenericTypeRepository
from app.calculate_generic_type.calculate_generic_type import CalculateGenericType


def main() -> None:
    if len(sys.argv) != 2:
        print("Gebruik: main <uuid van archief>")
        sys.exit(1)

    archiveuuid = sys.argv[1]
    
    try:
        error = CalculateGenericType().execute(archiveuuid)
    except Exception as e:
        print(f"Onverwachte fout: {e}")
        sys.exit(1)

    if error is not None:
        print(error)
        sys.exit(1)

if __name__ == "__main__":
    main()