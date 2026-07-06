"""M-perf — query-schaaltests op de full-text search (tsvector) laag: of
zoekqueries trager worden naarmate de database meer records bevat.

Perf 4.1 — Full-text search (tsvector) query-timing vs DB-grootte.

Story: "Blijft een zoekopdracht snel genoeg als het archief groeit van
honderden naar tienduizenden documenten?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC, gevuld via de bestaande
    modaldb_test database (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "fulltext_search") voor DB_ROW_COUNTS = [100, 1000, 10000], met db_row_count
  en db_size_mb automatisch meegelogd via get_db_stats(). DB wordt tussen
  parametrisaties opgeruimd (truncate) zodat elke test met een schone,
  gecontroleerde rijenteller start.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 4.1).
"""

# TODO(performance) — sectie 4.1: Full-text search (tsvector) query-timing vs DB-grootte
#
#   Maak tests/performance/queries/test_fulltext_search_scaling.py. Gebruik de bestaande
#   modaldb_test database. Definieer DB_ROW_COUNTS = [100, 1000, 10000] als constante.
#   Voor elk aantal: vul de test-DB op tot dat aantal rijen (via de bestaande ingest+NER-flow
#   op gegenereerde bestanden, of via directe bulk-insert als dat sneller is en de tabelstructuur
#   niet omzeilt op een manier die de query-test vervalst), roep dezelfde vaste full-text
#   search-query aan (bestaande tsvector-endpoint of repository-methode), meet met
#   measure_time(phase="fulltext_search", db_row_count=<n>) waarbij db_row_count en db_size_mb
#   automatisch via get_db_stats() worden meegelogd. Ruim de DB op tussen parametrisaties
#   (truncate) zodat elke test met een schone, gecontroleerde rijenteller start.

import pytest

pytestmark = pytest.mark.benchmark

DB_ROW_COUNTS = [100, 1000, 10000]

# TODO: test_fulltext_search_100rows, test_fulltext_search_1000rows, ... (zie prompt hierboven)
