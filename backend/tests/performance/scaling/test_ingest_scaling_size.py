"""M-perf — ingest-schaaltests op app/perform_tika_analysis/: hoe de ingest
(Tika-extractie) presteert naarmate bestanden groter worden.

Perf 2.1 — Ingest schaling per bestandsgrootte.

Story: "Hoe schaalt de ingest-tijd bij een vast aantal bestanden (10) en
oplopende grootte per bestand?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — dit is puur meten en loggen naar
  tests/performance/logs/benchmarks.jsonl (fase "ingest_by_size"), voor
  10 bestanden per grootte in SIZES_KB = [1, 10, 100, 1000, 10000, 100000].

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 2.1).
"""

# TODO(performance) — sectie 2.1: Ingest schaling per bestandsgrootte
#
#   Maak tests/performance/scaling/test_ingest_scaling_size.py. Gebruik pytest.mark.benchmark.
#   Definieer bovenaan het bestand een constante SIZES_KB = [1, 10, 100, 1000, 10000, 100000]
#   (1KB tot 100MB). Voor elke grootte: assembleer via assembler.py een manifest met 10 files
#   van die grootte (txt, geen ocr), roep de bestaande ingest_service (Tika-extractie) aan op
#   die folder, en meet de totale duur met measure_time(phase="ingest_by_size",
#   file_count=10, file_size_kb=<size>, total_corpus_kb=<size*10>, ocr_used=False).
#   Parametriseer de test met @pytest.mark.parametrize over SIZES_KB zodat elke grootte een
#   aparte, individueel faalbare test is (naamgeving test_ingest_size_1kb, test_ingest_size_10kb, ...).
#   Geen assert op een vaste drempel — dit is puur meten en loggen.

import pytest

pytestmark = pytest.mark.benchmark

SIZES_KB = [1, 10, 100, 1000, 10000, 100000]

# TODO: test_ingest_size_1kb, test_ingest_size_10kb, ... (zie prompt hierboven)
