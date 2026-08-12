# Use Case

Remove the LFM2 / `llama-cpp-python` integration entirely from the codebase. `llama-cpp-python` frequently has no prebuilt wheel for a given platform/Python combination, in which case `pip install` falls back to compiling from source — requiring `cmake` and a working C/C++ toolchain on every developer machine and in the Docker build. That's an unacceptable build-stability risk this close to the current deadline. This work is paused indefinitely (see `feature-context-llm-provider-abstraction-lfm2.md`, marked ON HOLD) — this feature cleans up what was already implemented from that context so the codebase has zero dependency on `llama-cpp-python`, cmake, or a C/C++ toolchain.

This is a pure removal/cleanup. Nothing about NER, Summary, or Topic Detection's actual behavior should change afterward — they should behave exactly as they did before LFM2 was introduced (spaCy-or-Ollama for NER, Ollama for Summary/Topics).

**Keep, do not remove:** the `LlmProvider` interface, `LlmProviderUnavailableError`, and `OllamaProvider` — none of these depend on `llama-cpp-python`, they're plain Python + `httpx`, and the flow controllers (`CreateNerForArchive`, `CreateTopicDetectionForArchive`, `CreateSummariesForArchive`) already depend on this abstraction rather than calling `ollama_client` directly. Removing these would be a much bigger regression than what's actually being asked for here.

# Business Rules

- Remove `llama-cpp-python` (and `huggingface_hub`, if it was ever added alongside it) from the backend's dependency list (`requirements.txt`/`pyproject.toml`).
- Delete `backend/app/shared/llm/llama_cpp_provider.py` entirely (the `LlamaCppProvider` class and the `llama_cpp_provider` singleton).
- In `backend/app/shared/analysis_engine_registry.py`:
    - Remove `_LLAMA_CPP_MODELS`.
    - Remove the import of `llama_cpp_provider`.
    - Remove `"llama_cpp"` from the `_PROVIDERS` dict — only `"ollama"` remains.
    - Simplify `classify_ner_engine()` back to a two-way check: spaCy (via `_SPACY_MODELS`) or Ollama (fallback default). Remove the `llama_cpp` branch.
    - Simplify `classify_llm_engine()` to always return `"ollama"` (it's currently only used by Summary/Topics, which now have exactly one engine kind again). Keep the function itself in place rather than removing it and inlining `"ollama"` at each call site — this keeps `CreateTopicDetectionForArchive`/`CreateSummariesForArchive` unchanged and keeps the door open for a future second provider without touching those files again.
- Remove the `llm_models_data` (or equivalently named) Docker volume from `docker-compose.yml` and `docker-compose.prod.yml`, and its mount from the backend service, if this was already added.
- Remove the `lfm_models_dir` setting from `backend/app/config.py`, if it was already added.
- After making these changes, search the codebase for any remaining references to confirm nothing is missed: `grep -rn "llama_cpp\|LlamaCpp\|llm_models_data\|lfm_models_dir" backend/` should return nothing.
- Verify the app still starts and NER/Summary/Topic Detection still run successfully afterward (via spaCy and Ollama respectively) — this confirms the removal didn't accidentally take the shared `LlmProvider`/`OllamaProvider` plumbing down with it.

# Component Overview

## Delete

- `backend/app/shared/llm/llama_cpp_provider.py`

## Modify

**`backend/app/shared/analysis_engine_registry.py`** — end state after cleanup:

```python
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
```

**`backend/app/config.py`** — remove the `lfm_models_dir` setting.

**`docker-compose.yml` / `docker-compose.prod.yml`** — remove the LFM models volume declaration and its mount on the backend service, if present.

**`requirements.txt` / `pyproject.toml`** — remove `llama-cpp-python` and `huggingface_hub`, if present.

## No changes needed

- **`LlmProvider`, `LlmProviderUnavailableError`** (`app/shared/llm/provider.py`) — untouched
- **`OllamaProvider`** (`app/shared/llm/ollama_provider.py`) — untouched
- **`CreateNerForArchive`, `CreateTopicDetectionForArchive`, `CreateSummariesForArchive`** — untouched; they already call `classify_*` / `get_llm_provider()` rather than referencing any provider directly, so they need no changes to keep working after this removal
- **`ner_llm_engine.py` (`run_ner_llm`)** — untouched; its `provider: LlmProvider` parameter is satisfied by `OllamaProvider` exactly as before
- **`ollama_client.py`, `ner_engine.py` (spaCy)** — untouched