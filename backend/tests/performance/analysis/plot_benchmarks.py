"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
verwerkt de verzamelde JSONL-data (logs/benchmarks.jsonl) tot visualisaties
en curve-fits voor extrapolatie (bv. naar 1GB / 10.000 files).

Wat we testen: niets — analyse/rapportage-script, geen test.

Vereisten om te draaien: geen (leest enkel logs/benchmarks.jsonl).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 6.1).
"""

# TODO(performance) — sectie 6.1: Plot-script
#
#   Maak tests/performance/analysis/plot_benchmarks.py met een CLI-script dat
#   tests/performance/logs/benchmarks.jsonl inleest via pandas (pd.read_json met lines=True),
#   en per "phase" een figuur genereert (matplotlib) met:
#   1. duration_sec vs file_size_kb (log-log schaal), met een gefitte curve
#      (probeer lineair en power-law fit via numpy.polyfit op log-log data, toon beide R²)
#   2. duration_sec vs file_count (log-log schaal), zelfde fit-aanpak
#   3. Voor phase="fulltext_search" en "vector_search": duration_sec vs db_row_count
#   Sla de figuren op als PNG in tests/performance/logs/plots/<phase>_<timestamp>.png.
#   Print ook de fit-parameters (zodat extrapolatie naar bv. 1GB/10.000 files mogelijk is
#   zonder de plot te hoeven aflezen).


def main() -> None:
    """CLI entry point: leest benchmarks.jsonl in en genereert plots + curve-fits per fase.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 6.1 in dit bestand")


if __name__ == "__main__":
    main()
