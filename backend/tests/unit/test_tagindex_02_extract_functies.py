"""
Run with:
    pytest tests/unit/test_tagindex_02_extract_functies.py -v

Tests for tag_index_engine.py — pure extract-functies, geen database nodig.

Story: "Zetten extract_ner_tags/extract_topics een Ner-/TopicDetection-rij correct om
naar (category, value, count)-tuples, ook als categorieën leeg zijn of het count-veld ontbreekt?"
"""

from types import SimpleNamespace

from app.create_tag_index_for_archive.tag_index_engine import extract_ner_tags, extract_topics


def _fake_ner(persons=None, locations=None, organisations=None, misc=None):
    return SimpleNamespace(
        persons=persons or [],
        locations=locations or [],
        organisations=organisations or [],
        misc=misc or [],
    )


def test_extract_ner_tags_over_meerdere_categorieen():
    ner_row = _fake_ner(
        persons=[{"entity": "Jan Janssens", "count": 1}],
        locations=[{"entity": "Gent", "count": 2}],
    )

    result = extract_ner_tags(ner_row)

    assert result == [
        ("persons", "Jan Janssens", 1),
        ("locations", "Gent", 2),
    ]


def test_extract_ner_tags_lege_categorieen():
    ner_row = _fake_ner()

    assert extract_ner_tags(ner_row) == []


def test_extract_ner_tags_ontbrekend_count_veld():
    ner_row = _fake_ner(misc=[{"entity": "Iets vaags"}])

    result = extract_ner_tags(ner_row)

    assert result == [("misc", "Iets vaags", 1)]


def test_extract_topics_normaal():
    topic_row = SimpleNamespace(topics=[{"topic": "belastingen", "count": 3}])

    assert extract_topics(topic_row) == [("belastingen", 3)]


def test_extract_topics_lege_lijst():
    topic_row = SimpleNamespace(topics=[])

    assert extract_topics(topic_row) == []


def test_extract_topics_ontbrekend_count_veld():
    topic_row = SimpleNamespace(topics=[{"topic": "stakingen"}])

    assert extract_topics(topic_row) == [("stakingen", 1)]
