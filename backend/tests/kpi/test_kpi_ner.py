"""KPI — Named Entity Recognition (NER)

Meet de kwaliteit van de NER-component (app/create_ner_for_archive/) op echte
archiefdata die door domeinexperts geannoteerd is.

Metrieken:
  - Precision  : van alle door het systeem gevonden entiteiten, hoeveel zijn correct?
  - Recall     : van alle door experts gemarkeerde entiteiten, hoeveel vindt het systeem?
  - F1-score   : harmonisch gemiddelde van precision en recall (hoofdmetrie)

Drempelwaarden staan in conftest.py en zijn aanpasbaar door domeinexperts.

Workflow voor domeinexperts:
  1. Voeg een archiefdocument toe aan tests/testdata/data_kpi/
  2. Voeg de verwachte entiteiten toe aan tests/testdata/data_kpi/annotaties_ner.json:
     {
       "bestandsnaam.txt": {
         "personen":   ["Jan Janssen", "Marie Declercq"],
         "locaties":   ["Antwerpen", "Brussel"],
         "organisaties": ["Gemeentearchief Gent"]
       }
     }
  3. De test pikt de annotaties automatisch op en berekent F1.

TODO: implementeren zodra:
  - Eerste set geannoteerde archiefdocumenten beschikbaar is
  - annotaties_ner.json aangemaakt is door domeinexperts
"""

import pytest


@pytest.mark.skip(reason="TODO: wachten op expert-annotaties in data_kpi/annotaties_ner.json")
def test_ner_f1_op_geannoteerde_archiefdata():
    """F1-score van NER op echte archiefdata ligt boven de drempelwaarde.

    Laadt expert-annotaties, verwerkt elk document via de NER-pipeline en
    berekent precision, recall en F1 over alle entiteitsklassen samen.
    """
    pass


@pytest.mark.skip(reason="TODO: wachten op expert-annotaties in data_kpi/annotaties_ner.json")
def test_ner_precision_personen():
    """Precision voor persoonsdetectie specifiek: weinig vals-positieven."""
    pass


@pytest.mark.skip(reason="TODO: wachten op expert-annotaties in data_kpi/annotaties_ner.json")
def test_ner_recall_locaties():
    """Recall voor locatiedetectie specifiek: weinig gemiste locaties."""
    pass
