"""Infrastructuur voor de performance-benchmarksuite (tests/performance/) —
genereert unieke referentiebestanden op exacte, parametriseerbare grootte,
zodat schaaltests (zie tests/performance/scaling/) reproduceerbare input hebben.

Wat we testen: niets — dit bestand test geen applicatiecode, het is de
generator die testdata produceert voor de rest van de suite.

Vereisten om te draaien: geen (geen DB/Tika/Ollama nodig, puur lokale
bestandsgeneratie).

TODO: nog te implementeren — zie de twee Claude Code-prompts hieronder
(MODAL_performance_benchmarks.md, secties 1.1 en 1.2).
"""

# TODO(performance) — sectie 1.1: Reference file generator
#
#   Maak tests/performance/reference_files/generator.py met een functie
#   generate_file(size_kb: int, index: int, filetype: str, output_dir: Path) -> Path
#   die een bestand genereert met representatieve Nederlandse tekst (gebruik een bronbestand
#   tests/performance/reference_files/text_source/sample_nl.txt met échte, betekenisvolle
#   Nederlandse tekst als basis, in stukken geknipt/gevarieerd zodat opeenvolgende bestanden
#   niet identiek zijn) tot precies size_kb kilobyte. Ondersteun filetype "txt", "pdf" en "docx"
#   (gebruik python-docx en reportlab of fpdf voor pdf). Voeg een CLI toe
#   (python generator.py --size-kb 100 --count 10 --type pdf --output-dir ...) zodat ik
#   reeksen kan genereren. Schrijf 1 pytest-test die verifieert dat het gegenereerde bestand
#   binnen 5% van de doelgrootte zit.
#
# TODO(performance) — sectie 1.2: Scan/OCR-variant generator (toevoegen aan dit bestand)
#
#   Maak tests/performance/reference_files/generator.py uit (voeg toe aan bestaand bestand)
#   een functie generate_scanned_pdf(size_kb: int, index: int, output_dir: Path) -> Path
#   die tekst uit sample_nl.txt rendert als afbeelding (bv. via PIL: tekst op een wit canvas
#   tekenen als bitmap) en die afbeelding(en) in een PDF plaatst, zodat er geen selecteerbare
#   tekstlaag in zit en Tika's OCR-pad wordt aangesproken. Zorg dat de output-grootte
#   vergelijkbaar is met de size_kb parameter (varieer resolutie/paginacount om dit te bereiken).
#   Voeg een CLI-optie toe aan de bestaande generator (--ocr-required flag).

from pathlib import Path


def generate_file(size_kb: int, index: int, filetype: str, output_dir: Path) -> Path:
    """Genereert een uniek bestand met representatieve NL-tekst van exact size_kb groot.

    TODO: implementeren volgens de prompt in sectie 1.1 hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.1 in dit bestand")


def generate_scanned_pdf(size_kb: int, index: int, output_dir: Path) -> Path:
    """Genereert een scan-PDF (tekst als afbeelding, geen tekstlaag) van ~size_kb groot.

    TODO: implementeren volgens de prompt in sectie 1.2 hierboven.
    """
    raise NotImplementedError("TODO: zie Claude Code-prompt sectie 1.2 in dit bestand")
