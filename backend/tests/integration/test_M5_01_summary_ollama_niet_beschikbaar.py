"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.01 — Summary-generatie als Ollama niet bereikbaar is.

Story: "Wat gebeurt er als Ollama niet bereikbaar is — duidelijke
foutmelding, geen crash?"

Wat we testen:
  generate() in ollama_client.py vangt een httpx.ConnectError op en
  gooit een OllamaUnavailableError. Deze test verifieert dat contract
  door de Ollama-URL tijdelijk naar een niet-luisterende poort te wijzen.

  We testen de fout op het niveau van de ollama_client, niet via de
  volledige CreateSummariesForArchive-orchestrator — die test zou een
  session_factory en een volledig archief vereisen.

Teststrategie:
  - monkeypatch op settings.ollama_url — geen mock van een service,
    maar een configuratiewijziging die de client naar een dode URL stuurt.
  - Geen database nodig: we testen de HTTP-foutafhandeling.
  - Ollama hoeft NIET te draaien — de test werkt juist wanneer die er niet is.

Vereist:
  - Niets (geen docker services)
"""

import pytest

from app.config import settings
from app.create_summaries_for_archive.ollama_client import OllamaUnavailableError, generate


@pytest.mark.asyncio
async def test_generate_gooit_ollama_unavailable_error_als_ollama_niet_bereikbaar_is(
    monkeypatch,
):
    """generate() gooit OllamaUnavailableError bij een ConnectError — geen crash."""
    # Wijs de URL naar een poort waarop zeker niets luistert.
    # monkeypatch herstelt de originele waarde na de test automatisch.
    monkeypatch.setattr(settings, "ollama_url", "http://localhost:1")

    with pytest.raises(OllamaUnavailableError, match="Ollama service unavailable"):
        await generate("llama3.2", "Vat samen: dit is een test.")

    print("\n[M5.01] OllamaUnavailableError correct gegooid bij onbereikbare service.")
