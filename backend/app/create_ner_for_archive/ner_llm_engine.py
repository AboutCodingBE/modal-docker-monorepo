import json
import logging

from app.shared.llm.provider import LlmProvider

_logger = logging.getLogger("app")

_ENTITY_CATEGORIES = ("persons", "locations", "organisations", "misc")


def _ner_prompt(text: str) -> str:
    return (
        "Je bent een AI die entiteiten herkent in tekst. Analyseer de onderstaande tekst.\n\n"
        "RICHTLIJNEN:\n"
        "- Identificeer: personen (persons), locaties (locations), organisaties (organisations), overige entiteiten (misc).\n"
        "- Geef GEEN inleiding, GEEN verklaring en GEEN markdown-codeblocks.\n\n"
        "Je MOET antwoorden in dit exacte JSON-formaat:\n"
        '{\n'
        '  "persons": ["naam1", "naam2"],\n'
        '  "locations": ["locatie1"],\n'
        '  "organisations": ["org1"],\n'
        '  "misc": []\n'
        '}\n\n'
        f"Tekst om te analyseren:\n\n{text}"
    )


async def run_ner_llm(text: str, model: str, provider: LlmProvider) -> dict:
    raw_response = await provider.generate(model, _ner_prompt(text), format="json")

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        _logger.warning("Invalid JSON returned by LLM NER — returning empty result.")
        data = {}

    result: dict = {}
    for cat in _ENTITY_CATEGORIES:
        items: list[str] = list(dict.fromkeys(
            v for v in data.get(cat, []) if isinstance(v, str)
        ))
        result[cat] = items
        result[f"{cat}_count"] = len(items)

    return result
