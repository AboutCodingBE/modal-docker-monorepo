"""M-perf — analyse-schaaltests op de summary-service (Ollama): hoe de
samenvattingstijd schaalt per bestandsgrootte.

Perf 3.2 — Summary-timing schaling.

Story: "Hoe verhoudt de summary-generatietijd zich naarmate documenten
groter worden?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Ollama bereikbaar op OLLAMA_URL (voor de warmed_up_model-fixture,
    zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "summary_scaling") per grootte in SIZES_KB, telkens warm
  (run_type="warm", na warmed_up_model).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 3.2).
"""

# TODO(performance) — sectie 3.2: Summary-timing schaling
#
#   Maak tests/performance/scaling/test_summary_scaling.py, naar analogie van
#   test_ner_scaling.py maar zonder model-loop (1 vast summary-model). Gebruik de
#   warmed_up_model fixture, SIZES_KB = [10, 100, 1000, 10000] als constante, file_count=10
#   vast. Voor elke grootte: assembleer, draai de bestaande summary-service, meet met
#   measure_time(phase="summary_scaling", file_count=10, file_size_kb=<size>, run_type="warm").
#   Parametriseer per size als aparte test.

import pytest

pytestmark = pytest.mark.benchmark

SIZES_KB = [10, 100, 1000, 10000]
FILE_COUNT = 10

# TODO: test_summary_scaling_10kb, test_summary_scaling_100kb, ... (zie prompt hierboven)
