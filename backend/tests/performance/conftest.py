"""Gedeelde fixtures voor de performance-benchmarksuite (tests/performance/).

Service-beschikbaarheid (requires_tika, requires_agent, requires_ollama, ...)
wordt geërfd van tests/conftest.py — dit bestand voegt enkel toe wat
specifiek is voor benchmarks: het opwarmen van een Ollama-model vóór een
meting, zodat cold-start de timing niet vervuilt.

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 1.4).
"""

# TODO(performance) — sectie 1.4: warmed_up_model fixture
#
#   Maak dit herbruikbaar als pytest fixture warmed_up_model(model_name) in
#   tests/performance/conftest.py, die warmup_model aanroept vóór de test en de duur
#   van de warm-up apart logt (niet meetellen in de testmeting zelf).
#   (zie tests/performance/fixtures/warmup.py voor warmup_model zelf)

import pytest


@pytest.fixture()
def warmed_up_model(request, requires_ollama):
    """Warmt het opgegeven Ollama-model op vóór de test en logt de warm-up-duur apart.

    Gebruik via indirect parametrize: @pytest.mark.parametrize("warmed_up_model", [...], indirect=True)

    TODO: implementeren volgens de prompt hierboven — roept
    fixtures.warmup.warmup_model(model_name, ollama_url) aan en logt de duur
    via fixtures.logger.log_benchmark(phase="warmup", ...).
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.4 in dit bestand")
