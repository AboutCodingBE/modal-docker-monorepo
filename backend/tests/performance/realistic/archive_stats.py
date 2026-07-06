"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
analyseert een écht archief om te checken of de synthetische testgrid
(SIZES_KB, COUNTS in tests/performance/scaling/) representatief is voor wat
klanten werkelijk aanleveren.

Wat we testen: niets direct — dit is een analyse-hulpmiddel, geen
testgenerator.

Vereisten om te draaien: geen (puur lokale bestandsscan van een opgegeven
archiefpad).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 5.1).
"""

# TODO(performance) — sectie 5.1: Archief-statistiekscript
#
#   Maak tests/performance/realistic/archive_stats.py met een CLI-script dat een pad naar
#   een échte archief-folder (bv. het VEA260 archief) als argument neemt, recursief alle
#   bestanden scant, en een rapport genereert (print + JSON-output naar
#   tests/performance/logs/archive_stats_<naam>.json) met: totaal aantal bestanden, totale
#   grootte, histogram van bestandsgroottes (bins: <10KB, 10-100KB, 100KB-1MB, 1-10MB, >10MB),
#   verdeling per bestandstype (extensie), en gemiddelde/mediaan/max bestandsgrootte.
#   Gebruik dit niet om nieuwe automatische tests te genereren — het is puur een
#   analyse-hulpmiddel om te bepalen of de constanten in scaling/*.py realistisch zijn.


def main() -> None:
    """CLI entry point: scant een archiefpad en schrijft een statistiekrapport.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 5.1 in dit bestand")


if __name__ == "__main__":
    main()
