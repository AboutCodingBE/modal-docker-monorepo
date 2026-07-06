"""M-perf — query-schaaltests op de vector search (pgvector) laag: of
semantic-searchqueries trager worden naarmate de database meer records bevat.

Perf 4.2 — Vector search (pgvector) query-timing vs DB-grootte.

Story: idem als 4.1, maar voor semantic/vector search — pas relevant zodra
de branch `dieter/semsearch` (embeddings-kolom) gemerged is.

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC, met een embeddings-kolom
    (pgvector) in het schema (zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "vector_search") voor dezelfde DB_ROW_COUNTS = [100, 1000, 10000] en
  meet/opruim-aanpak als test_fulltext_search_scaling.py.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 4.2). Blijft geskipt tot de
embeddings-kolom bestaat (zie skipif-conditie hieronder).
"""

# TODO(performance) — sectie 4.2: Vector search (pgvector) query-timing vs DB-grootte
#
#   Maak tests/performance/queries/test_vector_search_scaling.py, structureel identiek aan
#   test_fulltext_search_scaling.py maar met phase="vector_search" en de pgvector cosine-similarity
#   query in plaats van tsvector. Gebruik dezelfde DB_ROW_COUNTS = [100, 1000, 10000] constante
#   en dezelfde meet/opruim-aanpak. Markeer het bestand met een skip-conditie
#   (@pytest.mark.skipif) als de embeddings-kolom nog niet bestaat in het schema, zodat dit
#   pas actief wordt zodra de semsearch-migratie gemerged is.
#
# Let op: dit is de enige plek in tests/performance/ waar een skip-conditie wél
# is toegestaan — het gaat hier om een nog niet gemergede feature (schema bestaat
# nog niet), niet om een niet-bereikbare service (zie TESTING.md principe 2).

import pytest

pytestmark = pytest.mark.benchmark

DB_ROW_COUNTS = [100, 1000, 10000]

# TODO: skipif-conditie op het ontbreken van de embeddings-kolom, zie prompt hierboven.
# TODO: test_vector_search_100rows, test_vector_search_1000rows, ... (zie prompt hierboven)
