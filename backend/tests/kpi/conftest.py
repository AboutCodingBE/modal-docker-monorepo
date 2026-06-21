"""Gedeelde fixtures en drempelwaarden voor KPI-tests.

KPI-tests meten de kwaliteit van AI-componenten op echte archiefdata.
Ze geven geen binair geslaagd/mislukt maar een afstand van het ideale resultaat,
uitgedrukt in standaard NLP-metrieken zoals F1, ROUGE of Precision@K.

Drempelwaarden (thresholds) zijn bewust apart gedefinieerd zodat een
domeinexpert ze kan aanpassen zonder de testcode te wijzigen.
"""

# ---------------------------------------------------------------------------
# Drempelwaarden — aan te passen door domeinexperts
# ---------------------------------------------------------------------------

# NER — minimale F1-score (harmonic mean van precision en recall)
# F1 = 1.0 = perfect, F1 = 0.0 = geen enkele entiteit correct
NER_F1_DREMPEL = 0.70

# Samenvatting — minimale ROUGE-1 recall
# Hoeveel woorden uit de referentiesamenvatting zitten in de gegenereerde samenvatting?
SUMMARY_ROUGE1_DREMPEL = 0.40

# Zoeken — minimale Precision@5
# Hoeveel van de top-5 zoekresultaten zijn relevant?
SEARCH_PRECISION_AT_5_DREMPEL = 0.60
