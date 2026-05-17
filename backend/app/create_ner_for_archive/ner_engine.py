import spacy

_CHUNK_SIZE = 100_000

# Maps spaCy entity labels to our output categories
_LABEL_MAP = {
    "PER":  "persons",
    "ORG":  "organisations",
    "LOC":  "locations",
    "GPE":  "locations",
}

_nlp: spacy.language.Language | None = None


def _get_nlp(model: str) -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        _nlp = spacy.load(model, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])
    return _nlp


def run_ner(text: str, model: str = "nl_core_news_lg") -> dict:
    """Run spaCy NER on text and return deduplicated entity lists per category.

    Long texts are split into chunks of _CHUNK_SIZE characters to stay within
    spaCy's processing limits. Results from all chunks are merged and deduplicated.
    """
    nlp = _get_nlp(model)

    buckets: dict[str, list[str]] = {
        "persons": [],
        "locations": [],
        "organisations": [],
        "misc": [],
    }

    chunks = [text[i:i + _CHUNK_SIZE] for i in range(0, len(text), _CHUNK_SIZE)]

    for doc in nlp.pipe(chunks):
        for ent in doc.ents:
            value = ent.text.strip()
            if not value:
                continue
            category = _LABEL_MAP.get(ent.label_, "misc")
            if value not in buckets[category]:
                buckets[category].append(value)

    return {
        "persons":            buckets["persons"],
        "person_count":       len(buckets["persons"]),
        "locations":          buckets["locations"],
        "location_count":     len(buckets["locations"]),
        "organisations":      buckets["organisations"],
        "organisations_count": len(buckets["organisations"]),
        "misc":               buckets["misc"],
        "misc_count":         len(buckets["misc"]),
    }
