"""M-perf — realistische validatie: presteert het systeem op échte data zoals
verwacht op basis van de synthetische curves uit tests/performance/scaling/?

Perf 5.2 — Fixed realistische test-snapshot.

Story: sanity-check op een vaste, gekopieerde steekproef van een écht
archief (bv. VEA260) — dit is een validatiepunt, geen curve-fit-input.

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env)
  - Ollama bereikbaar op OLLAMA_URL (zie backend/.env)
  - Vaste snapshot-data in reference_files/realistic_snapshot/ (zie TODO
    hieronder — nog aan te maken bij implementatie van deze test)

Wat we testen:
  Eén test die de volledige ingest+NER+summary-flow op de snapshot draait
  en logt (fase "realistic_snapshot"). Geen assert op een vaste drempel.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 5.2).
"""

# TODO(performance) — sectie 5.2: Fixed realistische test-snapshot
#
#   Maak tests/performance/realistic/test_realistic_snapshot.py. Kopieer een vaste,
#   representatieve substeekproef van een écht archief (bv. 50 bestanden uit VEA260, manueel
#   gekozen of via een vast seed/selectie) naar tests/performance/reference_files/realistic_snapshot/
#   (commit dit in git als vaste testdata, na controle dat er geen gevoelige/vertrouwelijke
#   inhoud in zit). Schrijf 1 test die de volledige ingest+NER+summary-flow op deze snapshot
#   draait en logt met measure_time(phase="realistic_snapshot", file_count=50,
#   total_corpus_kb=<werkelijke grootte>). Dit is een validatiepunt, geen curve-fit-input —
#   voeg een code-comment toe die dit onderscheid expliciet maakt.

import pytest

pytestmark = pytest.mark.benchmark

# TODO: test_realistic_snapshot_ingest_ner_summary (zie prompt hierboven)
