"""M-perf — ingest-schaaltests op app/perform_tika_analysis/: combinatie van
bestandsaantal x grootte tot een realistisch totaalvolume (~1GB).

Perf 2.3 — Ingest schaling gecombineerd (realistisch tot 1GB).

Story: "Blijft het schaalgedrag consistent op realistische totaalvolumes,
ongeacht of dat volume uit veel kleine of weinig grote bestanden bestaat?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "ingest_combined") voor COMBINATIONS van (file_count, size_kb), telkens
  ongeveer 1_000_000 KB totaal.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 2.3).
"""

# TODO(performance) — sectie 2.3: Ingest schaling gecombineerd (realistisch tot 1GB)
#
#   Maak tests/performance/scaling/test_ingest_scaling_combined.py. Definieer een constante
#   COMBINATIONS = [(1000, 1000), (100, 10000), (10, 100000)] (tuples van (file_count, size_kb),
#   telkens neerkomend op ~1GB totaal — pas gerust de exacte tuples aan zodat totaal steeds
#   ongeveer 1_000_000 KB is). Voor elke combinatie: assembleer, draai ingest, meet met
#   measure_time(phase="ingest_combined", file_count=<n>, file_size_kb=<size>,
#   total_corpus_kb=<n*size>, ocr_used=False). Parametriseer als aparte tests, markeer alle
#   drie met @pytest.mark.slow naast @pytest.mark.benchmark.

import pytest

pytestmark = [pytest.mark.benchmark, pytest.mark.slow]

COMBINATIONS = [(1000, 1000), (100, 10000), (10, 100000)]

# TODO: test_ingest_combined_1000x1000kb, ... (zie prompt hierboven)
