"""Pure string-tests voor pad-normalisatie zoals gebruikt in folder_analysis.py.

Geen DB, geen fixtures, geen Docker — volledig zelfstandig uitvoerbaar:
  pytest backend/tests/unit/test_path_normalization.py -v

Context: de Windows-agent stuurt absolute_path met backslashes terug.
De Linux-container verwerkt die in folder_analysis.py via:
  full_path   = normalize_path(f["absolute_path"])
  parent_path = full_path.rsplit("/", 1)[0]

Deze tests documenteren en bewaken dat gedrag.

Story: "Geeft normalize_path Windows-backslashes correct om naar
forward slashes, zodat _parent_path altijd matcht met full_path van de
parent-map, ongeacht het besturingssysteem?"
"""

import os
import sys

from app.shared.path_utils import normalize_path


class TestPathNormalization:

    def test_01_windows_backslash_wordt_forward_slash(self):
        """normalize_path zet \\ om naar / — basisgedrag."""
        assert normalize_path("C:\\Users\\test\\bestand.txt") == "C:/Users/test/bestand.txt"

    def test_02_forward_slash_ongewijzigd(self):
        """normalize_path laat / ongemoeid — Mac/Linux paden blijven intact."""
        assert normalize_path("C:/Users/test/bestand.txt") == "C:/Users/test/bestand.txt"

    def test_03_gemengde_slashes(self):
        """Paden met mix van \\ en / worden volledig genormaliseerd."""
        assert normalize_path("C:/Users\\test/sub\\bestand.txt") == "C:/Users/test/sub/bestand.txt"

    def test_04_parent_path_berekening_uit_windows_pad(self):
        """De exacte berekening zoals folder_analysis.py die doet:
        eerst normalize_path, dan rsplit. Simuleert een Windows absolute_path
        zoals de agent die teruggeeft."""
        absolute_path = "C:\\Users\\drdwi\\Desktop\\archief\\communicatie\\brief.doc"
        result = normalize_path(absolute_path).rsplit("/", 1)[0]
        assert result == "C:/Users/drdwi/Desktop/archief/communicatie"

    def test_05_parent_path_een_niveau_diep(self):
        """Bestand direct in de root van het archief — parent is de archief-root zelf."""
        absolute_path = "C:\\Users\\drdwi\\Desktop\\archief\\brief.doc"
        result = normalize_path(absolute_path).rsplit("/", 1)[0]
        assert result == "C:/Users/drdwi/Desktop/archief"

    def test_06_parent_path_drie_niveaus_diep(self):
        """Bestand drie niveaus diep — parent_path is het volledige genormaliseerde
        pad van de directe parent."""
        absolute_path = "C:\\archief\\map_a\\map_b\\map_c\\bestand.jpg"
        result = normalize_path(absolute_path).rsplit("/", 1)[0]
        assert result == "C:/archief/map_a/map_b/map_c"

    def test_07_parent_path_matcht_full_path_van_map(self):
        """DE KERN VAN DE BUG: _parent_path van een bestand moet exact matchen
        met full_path van de parent-map. Dit test de volledige flow zoals
        path_to_id die gebruikt in FileRepository._persist_batch."""
        map_absolute  = "C:\\archief\\communicatie"
        file_absolute = "C:\\archief\\communicatie\\brief.doc"

        map_full_path    = normalize_path(map_absolute)
        file_parent_path = normalize_path(file_absolute).rsplit("/", 1)[0]

        assert map_full_path == file_parent_path, (
            f"MISMATCH: map full_path={map_full_path!r}, "
            f"file _parent_path={file_parent_path!r}"
        )

    def test_08_os_path_dirname_faalt_op_windows_paden_in_linux(self):
        """Documenteert het ORIGINELE BUG-GEDRAG: os.path.dirname op een
        Windows-pad (backslashes) in een Linux-omgeving geeft NIET de parent terug.

        VERWIJDER DEZE TEST NOOIT — het is de regressie-documentatie van de root cause.
        """
        absolute_path = "C:\\archief\\communicatie\\brief.doc"
        dirname_result = os.path.dirname(absolute_path)

        if sys.platform != "win32":
            # Op Linux/Mac: os.path.dirname herkent \\ niet als separator
            # en geeft het volledige pad terug (of een leeg segment)
            assert dirname_result != "C:\\archief\\communicatie", (
                f"os.path.dirname gedraagt zich onverwacht op {sys.platform}: "
                f"gaf {dirname_result!r} terug"
            )

            # De CORRECTE aanpak na de fix:
            correct_result = normalize_path(absolute_path).rsplit("/", 1)[0]
            assert correct_result == "C:/archief/communicatie"
