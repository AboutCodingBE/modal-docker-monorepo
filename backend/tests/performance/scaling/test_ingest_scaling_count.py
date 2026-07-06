"""M-perf — ingest-schaaltests op app/perform_tika_analysis/: hoe de ingest
(Tika-extractie) presteert naarmate het aantal bestanden toeneemt.

Perf 2.2 — Ingest schaling per bestandsaantal.

Story: "Hoe schaalt de ingest-tijd bij een vaste bestandsgrootte (10KB) en
oplopend aantal bestanden?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "ingest_by_count") voor COUNTS = [10, 100, 1000, 10000] bestanden van
  telkens 10KB.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 2.2).
"""

# TODO(performance) — sectie 2.2: Ingest schaling per bestandsaantal
#
#   Maak tests/performance/scaling/test_ingest_scaling_count.py, naar analogie van
#   test_ingest_scaling_size.py. Definieer COUNTS = [10, 100, 1000, 10000] als constante.
#   Voor elk aantal: assembleer een manifest met files van vaste grootte 10KB (txt, geen ocr),
#   draai ingest, meet met measure_time(phase="ingest_by_count", file_count=<count>,
#   file_size_kb=10, total_corpus_kb=<count*10>, ocr_used=False). Parametriseer per count
#   als aparte test. Waarschuw in een code-comment dat COUNTS=10000 lang kan duren en
#   overweeg dit als aparte, optioneel te skippen test met @pytest.mark.slow.

import pytest

pytestmark = pytest.mark.benchmark

COUNTS = [10, 100, 1000, 10000]

# TODO: test_ingest_count_10, test_ingest_count_100, ... (zie prompt hierboven)
# Let op: COUNTS=10000 kan lang duren — markeer die variant apart met
# @pytest.mark.slow zodat hij optioneel uitgesloten kan worden.
