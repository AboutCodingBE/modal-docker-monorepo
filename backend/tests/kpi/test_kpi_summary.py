"""KPI — Samenvatting (Summarization)

Meet de kwaliteit van de samenvattingscomponent op echte archiefdata die door
domeinexperts beoordeeld is.

Metrieken:
  - ROUGE-1 recall : hoeveel woorden uit de referentiesamenvatting zitten in de output?
  - ROUGE-2 recall : idem voor bigrammen (woordparen) — meet vloeiendheid
  - Semantische gelijkenis : cosine-afstand tussen embeddings van referentie en output

Drempelwaarden staan in conftest.py en zijn aanpasbaar door domeinexperts.

Workflow voor domeinexperts:
  1. Voeg een archiefdocument toe aan tests/testdata/data_kpi/
  2. Schrijf een referentiesamenvatting in tests/testdata/data_kpi/annotaties_summary.json:
     {
       "bestandsnaam.txt": "Dit document beschrijft de correspondentie tussen..."
     }
  3. De test vergelijkt de gegenereerde samenvatting met de referentie via ROUGE.

TODO: implementeren zodra:
  - Eerste set geannoteerde archiefdocumenten beschikbaar is
  - annotaties_summary.json aangemaakt is door domeinexperts
"""

import pytest


@pytest.mark.skip(reason="TODO: wachten op referentiesamenvattingen in data_kpi/annotaties_summary.json")
def test_summary_rouge1_op_geannoteerde_archiefdata():
    """ROUGE-1 recall van gegenereerde samenvattingen ligt boven de drempelwaarde."""
    pass


@pytest.mark.skip(reason="TODO: wachten op referentiesamenvattingen in data_kpi/annotaties_summary.json")
def test_summary_lengte_binnen_verwacht_bereik():
    """Gegenereerde samenvattingen zijn niet te kort (< 50 woorden) of te lang (> 300 woorden)."""
    pass
