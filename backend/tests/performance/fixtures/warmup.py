"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
warmt een Ollama-model op vóór een meting start, zodat cold-start (model
laden in VRAM/geheugen) de timing niet vervuilt.

Wat we testen: niets — infrastructuur.

Vereisten om te draaien: Ollama bereikbaar op OLLAMA_URL (zie backend/.env).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 1.4).
De pytest-fixture warmed_up_model hoort in tests/performance/conftest.py
(zie TODO aldaar).
"""

# TODO(performance) — sectie 1.4: Ollama warm-up functie
#
#   Maak tests/performance/fixtures/warmup.py met een functie
#   warmup_model(model_name: str, ollama_url: str) -> None
#   die één minimale dummy-call doet naar het opgegeven Ollama-model (bv. "geef één woord terug")
#   zodat het model geladen is in VRAM/geheugen vóór de echte meting start. Maak dit herbruikbaar
#   als pytest fixture warmed_up_model(model_name) in tests/performance/conftest.py, die warmup_model
#   aanroept vóór de test en de duur van de warm-up apart logt (niet meetellen in de testmeting zelf).


def warmup_model(model_name: str, ollama_url: str) -> None:
    """Doet een minimale dummy-call naar het model zodat het geladen is vóór de meting.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.4 in dit bestand")
