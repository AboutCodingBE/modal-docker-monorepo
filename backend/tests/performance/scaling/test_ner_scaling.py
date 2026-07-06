"""M-perf — analyse-schaaltests op app/create_ner_for_archive/: hoe de
NER-analysetijd schaalt per model en per bestandsgrootte.

Perf 3.1 — NER-timing schaling.

Story: "Hoe verhoudt de analysetijd van wikineural, GLiNER en de
Ollama-few-shot-variant zich tot elkaar naarmate documenten groter worden?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Ollama bereikbaar op OLLAMA_URL (voor de ollama_fewshot-variant en de
    warmed_up_model-fixture, zie backend/.env)

Wat we testen:
  Geen assert op een vaste drempel — puur meten en loggen (fase
  "ner_scaling") per combinatie van MODELS x SIZES_KB, telkens warm
  (run_type="warm", na warmed_up_model).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 3.1).
"""

# TODO(performance) — sectie 3.1: NER-timing schaling
#
#   Maak tests/performance/scaling/test_ner_scaling.py. Gebruik de warmed_up_model fixture
#   uit conftest.py vóór elke meting. Definieer MODELS = ["wikineural", "gliner", "ollama_fewshot"]
#   en SIZES_KB = [10, 100, 1000, 10000] als constanten, file_count=10 vast. Voor elke combinatie
#   van model × grootte: assembleer 10 files van die grootte, draai de bestaande NER-service
#   (gebruik de al geïmplementeerde ner_engine per model), meet met
#   measure_time(phase="ner_scaling", model_used=<model>, file_count=10, file_size_kb=<size>,
#   run_type="warm"). Parametriseer als aparte tests per (model, size)-combinatie.

import pytest

pytestmark = pytest.mark.benchmark

MODELS = ["wikineural", "gliner", "ollama_fewshot"]
SIZES_KB = [10, 100, 1000, 10000]
FILE_COUNT = 10

# TODO: test_ner_scaling_wikineural_10kb, ... (zie prompt hierboven)
