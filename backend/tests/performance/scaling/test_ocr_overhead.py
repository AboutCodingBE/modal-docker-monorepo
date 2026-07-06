"""M-perf — ingest-schaaltests op app/perform_tika_analysis/: de overhead die
OCR toevoegt aan de ingest-tijd.

Perf 2.4 — OCR aan/uit vergelijking.

Story: "Hoeveel trager is ingest wanneer Tika OCR moet toepassen (scan-PDF)
t.o.v. een zuivere tekst-PDF van dezelfde grootte?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "ingest_ocr_comparison") voor SIZES_KB = [10, 100, 1000, 10000], telkens
  1x met ocr_used=False en 1x met ocr_used=True.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 2.4).
"""

# TODO(performance) — sectie 2.4: OCR aan/uit vergelijking
#
#   Maak tests/performance/scaling/test_ocr_overhead.py. Gebruik SIZES_KB = [10, 100, 1000, 10000]
#   en file_count=10 vast. Voor elke grootte: draai de ingest twee keer — 1x met manifest
#   ocr_required=False (zuivere tekst-pdf) en 1x met ocr_required=True (scan-pdf via
#   generate_scanned_pdf). Log beide met measure_time(phase="ingest_ocr_comparison",
#   file_count=10, file_size_kb=<size>, ocr_used=<True/False>). Parametriseer over SIZES_KB,
#   zodat elke grootte 2 losse, vergelijkbare metingen oplevert in de log.

import pytest

pytestmark = pytest.mark.benchmark

SIZES_KB = [10, 100, 1000, 10000]
FILE_COUNT = 10

# TODO: test_ocr_overhead_10kb, test_ocr_overhead_100kb, ... (zie prompt hierboven)
