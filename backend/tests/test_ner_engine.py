"""
Run with:
    pytest tests/test_ner_engine.py -v

Tests for ner_engine.py — the spaCy NER component.

These tests do NOT require a database connection.
They verify that the NER engine correctly identifies named entities
in a Dutch sample text and returns them in the expected format.
"""

from app.create_ner_for_archive.ner_engine import run_ner

# Sample Dutch text containing known persons, a location and an organisation.
# We use this as input for all tests so we can predict what the output should be.
SAMPLE_TEXT = (
    "Jan Janssen schreef op 12 maart 1923 een brief aan Piet De Smet van Amsab-ISG in Gent. "
    "De brief handelt over de stakingen bij de Gentse textielfabrieken. "
    "Ook Marie Dupont van de socialistische partij wordt vermeld."
)


def test_ner_returns_expected_keys():
    """The result dict must always contain exactly these 8 keys — one list and one count per category."""
    result = run_ner(SAMPLE_TEXT)
    assert set(result.keys()) == {
        "persons", "person_count",
        "locations", "location_count",
        "organisations", "organisations_count",
        "misc", "misc_count",
    }


def test_ner_finds_persons():
    """At least one person should be detected in the sample text (Jan Janssen, Piet De Smet, Marie Dupont)."""
    result = run_ner(SAMPLE_TEXT)
    assert result["person_count"] > 0
    assert isinstance(result["persons"], list)


def test_ner_finds_locations():
    """'Gent' is explicitly mentioned and should appear in the locations list."""
    result = run_ner(SAMPLE_TEXT)
    assert result["location_count"] > 0
    assert any("Gent" in loc for loc in result["locations"])


def test_ner_counts_match_lists():
    """The _count fields must equal the actual length of their corresponding list.
    If this fails, the engine is reporting a wrong number."""
    result = run_ner(SAMPLE_TEXT)
    assert result["person_count"] == len(result["persons"])
    assert result["location_count"] == len(result["locations"])
    assert result["organisations_count"] == len(result["organisations"])
    assert result["misc_count"] == len(result["misc"])


def test_ner_no_duplicates():
    """Each entity should appear only once per category.
    Duplicates would distort counts and pollute search results."""
    result = run_ner(SAMPLE_TEXT)
    for key in ("persons", "locations", "organisations", "misc"):
        assert len(result[key]) == len(set(result[key]))
