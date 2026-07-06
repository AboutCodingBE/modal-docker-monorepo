"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
de kernlogger van de hele suite: meet de duur van een fase en schrijft die,
samen met git-commit, DB-statistieken en context-velden, weg als append-only
JSONL-regel naar tests/performance/logs/benchmarks.jsonl.

Wat we testen: niets — infrastructuur.

Vereisten om te draaien: PostgreSQL bereikbaar op DATABASE_URL_SYNC voor
get_db_stats() (zie backend/.env).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 1.5).
"""

# TODO(performance) — sectie 1.5: Timing decorator + JSONL-writer
#
#   Maak tests/performance/fixtures/logger.py met:
#   1. Een functie get_git_commit() -> str die "git rev-parse --short HEAD" uitvoert.
#   2. Een functie get_db_stats(connection) -> dict die pg_database_size(datname) en
#      een rijentelling (COUNT(*)) van de relevante tabellen (files, ner_results,
#      summaries) ophaalt en teruggeeft als {"db_size_mb": float, "db_row_count": dict}.
#   3. Een functie log_benchmark(phase: str, duration_sec: float, **extra_fields) die een
#      dict samenstelt met velden: timestamp (ISO), git_commit, phase, duration_sec, en
#      alle extra_fields (bv. file_count, file_size_kb, total_corpus_kb, ocr_used, model_used,
#      device, run_type, db_size_mb, db_row_count, manifest_id), en dit als 1 regel JSON
#      append naar tests/performance/logs/benchmarks.jsonl.
#   4. Een context manager measure_time(phase, **extra_fields) die start/stop timet met
#      time.perf_counter() en automatisch log_benchmark aanroept bij het verlaten van de
#      context, ook bij een exception (log dan met duration_sec en een extra veld "failed": true).
#   Schrijf een unit test die verifieert dat measure_time() een correcte regel toevoegt
#   aan een tijdelijk logbestand.

from contextlib import contextmanager


def get_git_commit() -> str:
    """Geeft de korte git-commit hash van HEAD terug (git rev-parse --short HEAD).

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.5 in dit bestand")


def get_db_stats(connection) -> dict:
    """Haalt db_size_mb en db_row_count (per tabel) op via de gegeven DB-connectie.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.5 in dit bestand")


def log_benchmark(phase: str, duration_sec: float, **extra_fields) -> None:
    """Append één JSON-regel met de meting aan tests/performance/logs/benchmarks.jsonl.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.5 in dit bestand")


@contextmanager
def measure_time(phase: str, **extra_fields):
    """Timet een codeblok met time.perf_counter() en logt het resultaat via log_benchmark.

    TODO: implementeren volgens de prompt hierboven (inclusief exception-pad
    met "failed": true).
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.5 in dit bestand")
    yield  # pragma: no cover — onbereikbaar tot implementatie
