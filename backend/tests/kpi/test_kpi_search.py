"""KPI — Zoekresultaten (Full-text search)

Meet de kwaliteit van de zoekfunctie (app/ M4) op echte archiefdata met
door domeinexperts beoordeelde relevantie.

Metrieken:
  - Precision@K : van de top-K resultaten, hoeveel zijn relevant?
  - Recall@K    : van alle relevante documenten, hoeveel zitten in de top-K?
  - MRR         : Mean Reciprocal Rank — hoe hoog staat het eerste relevante resultaat?

Drempelwaarden staan in conftest.py en zijn aanpasbaar door domeinexperts.

Workflow voor domeinexperts:
  1. Stel een zoekterm op en markeer welke documenten in het archief relevant zijn
  2. Voeg toe aan tests/testdata/data_kpi/annotaties_search.json:
     {
       "uitnodiging picknick": {
         "relevant": ["UITNODIGING_via_post.doc", "programma_zomer_2007.pdf"],
         "niet_relevant": ["Speellijst_lanceerv_huiskamerv_2007.xls"]
       }
     }
  3. De test voert de zoekopdracht uit en berekent Precision@K en MRR.

TODO: implementeren zodra:
  - Zoekfunctionaliteit (M4) volledig geïmplementeerd is
  - Expert-annotaties beschikbaar zijn in data_kpi/annotaties_search.json
"""

import pytest


@pytest.mark.skip(reason="TODO: wachten op expert-annotaties in data_kpi/annotaties_search.json")
def test_search_precision_at_5():
    """Minstens 60% van de top-5 zoekresultaten is relevant volgens experts."""
    pass


@pytest.mark.skip(reason="TODO: wachten op expert-annotaties in data_kpi/annotaties_search.json")
def test_search_mrr():
    """Het eerste relevante resultaat staat gemiddeld in de top-3 (MRR > 0.33)."""
    pass
