"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
zet een manifest (welke combinatie van referentiebestanden) om in een
tijdelijke ingest-folder, zodat schaaltests niet telkens opnieuw testdata
moeten genereren.

Wat we testen: niets — infrastructuur. Zie tests/performance/manifests/
voor het JSON-schema en de concrete manifest-bestanden.

Vereisten om te draaien: geen (puur lokale bestandsgeneratie/-caching via
reference_files/generator.py).

TODO: nog te implementeren — zie Claude Code-prompt hieronder
(MODAL_performance_benchmarks.md, sectie 1.3).
"""

# TODO(performance) — sectie 1.3: Manifest-systeem
#
#   Maak tests/performance/manifests/ met een JSON-schema voor manifests:
#   {
#     "manifest_id": "string",
#     "files": [{"size_kb": int, "count": int, "filetype": "txt|pdf|docx", "ocr_required": bool}]
#   }
#   Maak tests/performance/fixtures/assembler.py met een functie
#   assemble_from_manifest(manifest_path: Path, tmp_dir: Path) -> Path
#   die: 1) het manifest inleest, 2) voor elke file-spec de generator uit generator.py aanroept
#   als het bestand nog niet in reference_files/generated/ bestaat (cache op basis van
#   size_kb+index+filetype+ocr_required in de bestandsnaam), 3) de bestanden naar tmp_dir kopieert.
#   Genereer ook 3 concrete manifest-bestanden:
#   - batch_10files_10kb.json (10 files x 10kb, txt)
#   - batch_100files_10kb.json (100 files x 10kb, txt)
#   - batch_10files_mixed_ocr.json (10 files, helft txt helft ocr-required, 10kb elk)
#   Schrijf 1 test die assemble_from_manifest aanroept en verifieert dat het juiste aantal
#   bestanden in tmp_dir terechtkomt.

from pathlib import Path


def assemble_from_manifest(manifest_path: Path, tmp_dir: Path) -> Path:
    """Bouwt een ingest-folder op basis van een manifest (JSON) in tmp_dir.

    TODO: implementeren volgens de prompt hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.3 in dit bestand")
