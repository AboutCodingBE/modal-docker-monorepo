from app.shared.llm.ollama_provider import ollama_provider
from app.shared.llm.provider import LlmProvider

_SPACY_MODELS = {"nl_core_news_lg"}

_PROVIDERS: dict[str, LlmProvider] = {
    "ollama": ollama_provider,
}


def classify_ner_engine(model: str) -> str:
    if model in _SPACY_MODELS:
        return "spacy"
    return "ollama"


def classify_llm_engine(model: str) -> str:
    return "ollama"


def get_llm_provider(engine_kind: str) -> LlmProvider:
    provider = _PROVIDERS.get(engine_kind)
    if provider is None:
        raise ValueError(f"Unknown LLM engine kind: {engine_kind}")
    return provider
