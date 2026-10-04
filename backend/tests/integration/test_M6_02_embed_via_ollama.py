"""M6.02 — embed() tegen de echte Ollama-service.

Test app/shared/ollama_client.py::embed(), de laag-niveau HTTP-aanroep naar
Ollama's /api/embed endpoint die tekst omzet naar een embedding-vector.

We testen hier bewust NIET op exacte vector-waarden — embeddingmodellen zijn niet
zomaar reproduceerbaar te asserten en de exacte getallen zeggen niets over
correctheid. In plaats daarvan testen we structurele eigenschappen: de juiste
dimensie, en dat semantisch gelijkaardige tekst dichter bij elkaar ligt
(hogere cosine-similarity) dan ongerelateerde tekst.

Vereiste services: Ollama, met het model uit settings.embedding_model al gepulled
(`ollama pull qwen3-embedding:0.6b`), zie de requires_ollama-fixture in conftest.py.
"""

import math

import pytest

from app.config import settings
from app.shared.ollama_client import embed


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Standaard cosine-similarity, in pure Python — geen numpy-dependency nodig voor één testhulpfunctie."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot_product / (norm_a * norm_b)


@pytest.mark.asyncio
async def test_embed_geeft_vector_met_juiste_dimensie(requires_ollama):
    """De teruggegeven vector moet exact settings.embedding_dimension getallen bevatten —
    anders past hij niet in de embeddings-tabel (VECTOR(n) in migratie 0017)."""
    vector = await embed(settings.embedding_model, "Dit is een testzin voor embedding.")

    assert len(vector) == settings.embedding_dimension
    assert all(isinstance(waarde, float) for waarde in vector)


@pytest.mark.asyncio
async def test_embed_gelijkaardige_zinnen_liggen_dichter_bij_elkaar_dan_ongerelateerde(requires_ollama):
    """Sanity-check voor semantic search: twee zinnen over hetzelfde onderwerp moeten een
    hogere cosine-similarity hebben dan twee zinnen over totaal verschillende onderwerpen.
    Als dit faalt, is het model niet bruikbaar voor semantic search — ongeacht of de
    HTTP-aanroep zelf werkt."""
    origineel = await embed(settings.embedding_model, "De kat zit op de mat in de woonkamer.")
    gelijkaardig = await embed(settings.embedding_model, "Een poes ligt op het tapijt in de living.")
    ongerelateerd = await embed(settings.embedding_model, "De aandelenkoers steeg met tien procent vandaag.")

    similarity_gelijkaardig = _cosine_similarity(origineel, gelijkaardig)
    similarity_ongerelateerd = _cosine_similarity(origineel, ongerelateerd)

    assert similarity_gelijkaardig > similarity_ongerelateerd, (
        f"Verwacht dat gelijkaardige tekst dichter bij elkaar ligt: "
        f"gelijkaardig={similarity_gelijkaardig:.4f}, ongerelateerd={similarity_ongerelateerd:.4f}"
    )
