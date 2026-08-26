"""
Run with:
    pytest tests/unit/test_M6_02_chunk_text.py -v

Tests for chunk_text() in app/create_embeddings_for_archive/embedding_engine.py —
de pure functie die brontekst opsplitst in chunks vóór het embedden.

Deze tests vereisen geen database of Ollama: chunk_text() is een pure functie
die enkel op de string zelf werkt (woord-gebaseerd, geen echte tokenizer).

Story: "Geeft chunk_text() correcte, niet-overlappende chunks terug voor lege
tekst, tekst korter dan chunk_size, tekst die exact een veelvoud van
chunk_size is, en tekst die enkel uit witruimte bestaat? En wordt een te kort
laatste restje (< helft van chunk_size) samengevoegd met de voorlaatste chunk,
zodat er geen piepklein, weinig betekenisvol staartje apart embed wordt?"
"""

from app.create_embeddings_for_archive.embedding_engine import chunk_text


def test_chunk_text_lege_tekst_geeft_geen_chunks():
    """Lege tekst bevat geen woorden, dus moet er een lege lijst terugkomen — geen chunk met lege string."""
    result = chunk_text("", chunk_size=5)
    assert result == []


def test_chunk_text_whitespace_only_geeft_geen_chunks():
    """Enkel spaties/tabs/newlines bevatten geen woorden na split() — zelfde resultaat als lege tekst."""
    result = chunk_text("   \n\t  \n", chunk_size=5)
    assert result == []


def test_chunk_text_korter_dan_chunk_size_geeft_één_chunk():
    """Als de tekst minder woorden heeft dan chunk_size, moet alles in één enkele chunk terechtkomen."""
    result = chunk_text("een twee drie", chunk_size=10)
    assert result == ["een twee drie"]


def test_chunk_text_exact_veelvoud_geeft_gelijke_chunks_zonder_rest():
    """Bij een tekst met exact 2 * chunk_size woorden mogen er geen lege of onvolledige
    laatste chunk overblijven — precies 2 chunks van elk chunk_size woorden."""
    woorden = [f"woord{i}" for i in range(6)]
    tekst = " ".join(woorden)

    result = chunk_text(tekst, chunk_size=3)

    assert result == ["woord0 woord1 woord2", "woord3 woord4 woord5"]


def test_chunk_text_te_kort_laatste_restje_wordt_samengevoegd_met_vorige_chunk():
    """Als de laatste chunk minder dan de helft van chunk_size woorden bevat (hier: 1 van 3),
    moet hij samengevoegd worden met de voorlaatste chunk — geen piepklein, weinig
    betekenisvol staartje dat op zichzelf embed wordt."""
    woorden = [f"woord{i}" for i in range(7)]
    tekst = " ".join(woorden)

    result = chunk_text(tekst, chunk_size=3)

    assert result == ["woord0 woord1 woord2", "woord3 woord4 woord5 woord6"]


def test_chunk_text_restje_van_precies_de_helft_blijft_apart():
    """Bij een restje van exact de helft van chunk_size (hier: 2 van 4) wordt NIET
    samengevoegd — de drempel is 'strikt minder dan de helft', dus dit is de grens
    waarop het nog als 'lang genoeg' telt."""
    woorden = [f"woord{i}" for i in range(6)]
    tekst = " ".join(woorden)

    result = chunk_text(tekst, chunk_size=4)

    assert result == ["woord0 woord1 woord2 woord3", "woord4 woord5"]


def test_chunk_text_met_slechts_1_chunk_wordt_nooit_samengevoegd():
    """Als de hele tekst in 1 chunk past, is er geen voorlaatste chunk om mee samen
    te voegen — die ene chunk blijft gewoon staan, ook al is hij zelf 'kort'."""
    result = chunk_text("een woord", chunk_size=10)
    assert result == ["een woord"]


def test_chunk_text_laat_geen_woorden_vallen_of_dupliceren():
    """Alle woorden uit de brontekst moeten terug te vinden zijn in de chunks samen,
    in dezelfde volgorde en zonder duplicaten — anders verliest of dupliceert search-content."""
    woorden = [f"woord{i}" for i in range(11)]
    tekst = " ".join(woorden)

    result = chunk_text(tekst, chunk_size=4)

    heropgebouwd = " ".join(result).split()
    assert heropgebouwd == woorden
