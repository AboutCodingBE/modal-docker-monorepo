# We extraheren info uit een ner of topic row hoe zien die eruit?
# Input-vorm (zie backend/app/shared/models.py):
#   Ner: persons/locations/organisations/misc, elk een lijst van dicts,
#        bv. persons = [{"entity": "Jan Janssens", "count": 1}, ...]
#   TopicDetection: topics, ook een lijst van dicts,
#        bv. topics = [{"topic": "belastingen", "count": 1}, ...]

_NER_CATEGORIES = ("persons", "locations", "organisations", "misc")


def extract_ner_tags(ner_row) -> list[tuple[str, str, int]]:
    """
        (category, value, count) uit een Ner-rij, over de 4 categorieën heen. ner_row 4x lijst van pairs (term, freq)
    """

    result = []
    for category in _NER_CATEGORIES:

        # getattr(ner_row, "persons") == ner_row.persons, maar dan met de attribuutnaam als var
        for item in getattr(ner_row, category) or []:
            result.append((category, item["entity"], item.get("count", 1)))

    return result


def extract_topics(topic_row) -> list[tuple[str, int]]:
    """
        (value, count) uit een TopicDetection-rij. (topic_row.topics is een lijst van pairs)
    """
    return [(item["topic"], item.get("count", 1)) for item in (topic_row.topics or [])]
