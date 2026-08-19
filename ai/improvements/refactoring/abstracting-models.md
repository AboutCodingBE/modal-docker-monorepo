# Deferred Work (do not implement now, but do not lose track of it either)

This context deliberately does **not** touch the database. Model *classification* ("is `X` a spaCy model, an Ollama model, or an LFM2 model?") is implemented here as a temporary static allow-list, mirroring the `_SPACY_MODELS` set already introduced for NER dispatch. This is a known placeholder for a future feature: extending `analysis_configuration` (or a new table) so that adding a new selectable model — especially a new Ollama or LFM2 model — is a data change, not a code change, and so the analysis-configuration modal can show a "default" per type. That DB/UI work is out of scope here and should be picked up as its own context later. The only thing this context guarantees is that when that DB work happens, only the *classification* functions in `analysis_engine_registry.py` need to change — nothing about `LlmProvider`, `OllamaProvider`, `LlamaCppProvider`, or any flow controller should need to change as a result.

This context also does **not** implement downloading LFM2 model files. `LlamaCppProvider` only loads a model if its GGUF file already exists in `lfm_models_dir` — it does not fetch anything over the network. Acquiring model files (whether that ends up being download-on-first-select, an explicit "download" action in a settings UI, or something else) is intentionally deferred to the upcoming settings feature, since how/when a download is triggered is a UX decision that feature owns, not this one. For now, getting a model file into `lfm_models_dir` is a manual/out-of-band step (e.g. placed there directly during development/testing).

# Use Case

Introduce `LlamaCppProvider` (LFM2 via `llama-cpp-python`) as a second implementation of the `LlmProvider` abstraction, alongside the existing Ollama path, usable for all three analysis types (NER, Summary, Topic Detection). This requires:

1. A formal `LlmProvider` interface, so prompt-building/parsing code (the `_ner_prompt`/`run_ner_llm`, `_topic_prompt`, and the summary equivalent) stops calling `app.shared.ollama_client.generate()` directly and instead calls an injected provider — making Ollama and LFM2 interchangeable from the caller's point of view.
2. `OllamaProvider` — a thin adapter wrapping the existing `ollama_client.generate()`.
3. `LlamaCppProvider` — loads GGUF models via `llama-cpp-python` from a dedicated persistent directory. This context does **not** implement downloading — it only loads a model file if one already exists at the expected path, and fails clearly (via `LlmProviderUnavailableError`) otherwise. It caches loaded model instances in-process (avoiding the `_get_nlp()`-style bug where a cache ignores which model was actually requested).
4. A small classification registry that decides, given a `model` string: for NER, is this spaCy, Ollama, or LFM2? For Summary/Topics, is this Ollama or LFM2? This registry is intentionally the *only* place that will need to change once model selection becomes DB-driven.

This is a pure abstraction/plumbing feature. No new model is actually exposed to end users yet (same caveat as the earlier NER-via-Ollama context) — this makes the backend *capable* of running any of the three analysis types via LFM2, using the same static-allow-list mechanism as everything else so far.

# Business Rules

## LlmProvider interface

- `LlmProvider` is an abstract interface with one method: `async def generate(self, model: str, prompt: str, format: str | None = None) -> str`. Same signature shape as today's free-function `generate()`, just made polymorphic.
- Introduce one shared exception, `LlmProviderUnavailableError`, raised by any provider when it cannot fulfill a request (Ollama unreachable, LFM2 model failed to download/load). Flow controllers must catch this one exception type generically to trigger the existing "abort the whole run" behavior — they must not need to know which concrete provider is in use or catch provider-specific exceptions individually.
- `OllamaProvider.generate()` must catch the existing `OllamaUnavailableError` (from `app.shared.ollama_client`) internally and re-raise it as `LlmProviderUnavailableError`, so `ollama_client.py` itself does not need to change.

## LlamaCppProvider — storage and loading (no download in this context)

- Models are stored in a dedicated directory, configured via a new setting `lfm_models_dir` (default `/app/models/lfm`).
- This directory must be backed by a new named Docker volume (analogous to `ollama_data`), added to both `docker-compose.yml` and `docker-compose.prod.yml`, and mounted into the backend service (the container that will actually run `llama-cpp-python`). This volume is provisioned now so it's ready for whenever the download mechanism lands, even though nothing writes to it yet as part of this context.
- `LlamaCppProvider` does **not** download anything. Given a model's repo id, it resolves the expected file path (`lfm_models_dir / <filename from the registry>`) and checks whether it exists.
    - If the file exists, load it.
    - If the file does not exist, raise `LlmProviderUnavailableError` with a clear message stating the model isn't downloaded yet (this is a legitimate, expected outcome right now, not a bug) — this must trigger the same "abort the run" handling as an unreachable Ollama, since there's no way to proceed without the file.
- Use a per-model `asyncio.Lock` (keyed by model repo id) around the load step, so two concurrent analysis runs requesting the same not-yet-loaded model don't both attempt to load it into memory redundantly.

## LlamaCppProvider — loading and inference

- Cache loaded `Llama` instances in a `dict[str, Llama]` keyed by the model's repo id, **not** a single global (this is the exact bug already flagged in `ner_engine.py`'s `_get_nlp()` — do not repeat it here).
- Model loading (`Llama(model_path=...)`) is itself expensive and blocking — also run via `asyncio.to_thread`.
- `generate()` itself calls `create_chat_completion()` (or the equivalent completion call), also via `asyncio.to_thread`, since `llama-cpp-python` inference is synchronous/CPU-bound.
- When `format == "json"` is requested, use whatever constrained/structured output mechanism the installed `llama-cpp-python` version actually supports for JSON (e.g. a JSON-schema response format, or grammar-based constrained decoding) — confirm the exact parameter name against the installed version's docs/changelog before finalizing, API surface for this has changed across `llama-cpp-python` releases and should not be assumed from memory.

## Classification registry

- New module `app/shared/analysis_engine_registry.py`, replacing the `_SPACY_MODELS` constant currently living in `create_ner_for_archive.py` (move it here) and introducing a new `_LLAMA_CPP_MODELS` mapping of `repo_id -> filename` (the filename is needed for `hf_hub_download`).
- Expose:
    - `classify_ner_engine(model: str) -> str` — returns `"spacy"`, `"llama_cpp"`, or `"ollama"` (fallback default, same philosophy as today's implicit "anything not spaCy is Ollama").
    - `classify_llm_engine(model: str) -> str` — returns `"llama_cpp"` or `"ollama"` (used by Summary and Topics, which never have a library option).
    - `get_llm_provider(engine_kind: str) -> LlmProvider` — returns the singleton `OllamaProvider` or `LlamaCppProvider` instance for a given engine kind; raises `ValueError` for an unknown kind (should not happen in practice, since the classify functions only ever return known kinds, but fail loudly rather than silently if it does).
- These are the **only** functions that should ever need to change when model selection becomes DB-driven later. Every call site should depend on `classify_*` / `get_llm_provider`, never on the underlying allow-list constants directly.

## Flow controller updates

- `CreateNerForArchive`: replace the two-way `if model in _SPACY_MODELS` check with `classify_ner_engine(model)`, branching three ways (spaCy / Ollama / llama_cpp). The Ollama and llama_cpp branches both resolve a provider via `get_llm_provider()` and pass it into `run_ner_llm()`. Catch `LlmProviderUnavailableError` instead of the current `OllamaUnavailableError`-specific catch, so both providers get the same "abort the run" treatment.
- `CreateTopicDetectionForArchive`: same idea — resolve `classify_llm_engine(model)` → `get_llm_provider()`, call `provider.generate(model, _topic_prompt(text), format="json")` instead of calling `ollama_client.generate()` directly. Catch `LlmProviderUnavailableError` in place of `OllamaUnavailableError`.
- `CreateSummariesForArchive` — this file wasn't shared in this conversation, so its exact current structure is an assumption. It should follow the identical pattern (resolve provider via `classify_llm_engine`/`get_llm_provider`, call `provider.generate(...)` instead of a direct `ollama_client`/`generate` import, catch `LlmProviderUnavailableError`). Confirm its actual current code before applying — the shape of the change should mirror the topic-detection change above almost line for line.
- `run_ner_llm()` (`app/create_ner_for_archive/ner_llm_engine.py`, added in the earlier NER-via-Ollama context) changes signature from `run_ner_llm(text, model)` to `run_ner_llm(text, model, provider: LlmProvider)`, calling `await provider.generate(model, _ner_prompt(text), format="json")` instead of importing `generate` from `ollama_client` directly.

## New dependency

- Add `llama-cpp-python` to the backend's dependency list (`requirements.txt`/`pyproject.toml`, whichever this project uses). Note from the original research: the compiled backend differs per platform (CPU-only by default; CUDA build available via `CMAKE_ARGS="-DGGML_CUDA=on"` at install time) — per the earlier decision to stay Docker-contained for now, no GPU build flags are needed yet, plain CPU install is sufficient.
- `huggingface_hub` is **not** needed by this context, since downloading is out of scope — it will be added when the download mechanism itself is implemented as part of the settings feature.

# Component Overview

## LlmProvider interface + shared exception

**New file:** `backend/app/shared/llm/provider.py`

```python
from abc import ABC, abstractmethod


class LlmProviderUnavailableError(Exception):
    """Raised by any LlmProvider implementation when it cannot fulfill a request."""


class LlmProvider(ABC):
    @abstractmethod
    async def generate(self, model: str, prompt: str, format: str | None = None) -> str:
        ...
```

## OllamaProvider

**New file:** `backend/app/shared/llm/ollama_provider.py`

```python
from app.shared.llm.provider import LlmProvider, LlmProviderUnavailableError
from app.shared.ollama_client import OllamaUnavailableError, generate


class OllamaProvider(LlmProvider):
    async def generate(self, model: str, prompt: str, format: str | None = None) -> str:
        try:
            return await generate(model, prompt, format)
        except OllamaUnavailableError as e:
            raise LlmProviderUnavailableError(str(e)) from e


ollama_provider = OllamaProvider()
```

## LlamaCppProvider

**New file:** `backend/app/shared/llm/llama_cpp_provider.py`

```python
import asyncio
from pathlib import Path

from llama_cpp import Llama

from app.config import settings
from app.shared.llm.provider import LlmProvider, LlmProviderUnavailableError


class LlamaCppProvider(LlmProvider):
    def __init__(self):
        self._models: dict[str, Llama] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def generate(self, model: str, prompt: str, format: str | None = None) -> str:
        """`model` is the Hugging Face repo id, e.g. 'LiquidAI/LFM2-2.6B-GGUF'."""
        try:
            llm = await self._get_or_load(model)
            return await asyncio.to_thread(self._run_completion, llm, prompt, format)
        except LlmProviderUnavailableError:
            raise
        except Exception as e:
            raise LlmProviderUnavailableError(f"LFM2 generation failed for {model}: {e}") from e

    async def _get_or_load(self, repo_id: str) -> Llama:
        if repo_id in self._models:
            return self._models[repo_id]

        lock = self._locks.setdefault(repo_id, asyncio.Lock())
        async with lock:
            if repo_id in self._models:  # re-check after acquiring the lock
                return self._models[repo_id]

            model_path = self._resolve_model_path(repo_id)
            if not model_path.exists():
                raise LlmProviderUnavailableError(
                    f"LFM2 model '{repo_id}' is not downloaded yet. Downloading "
                    "is not supported by this provider — it will be available "
                    "via the upcoming model settings feature."
                )

            llm = await asyncio.to_thread(Llama, model_path=str(model_path), n_ctx=4096)
            self._models[repo_id] = llm
            return llm

    @staticmethod
    def _resolve_model_path(repo_id: str) -> Path:
        from app.shared.analysis_engine_registry import _LLAMA_CPP_MODELS  # filename lookup

        filename = _LLAMA_CPP_MODELS.get(repo_id)
        if filename is None:
            raise LlmProviderUnavailableError(f"Unknown LFM2 model repo id: {repo_id}")
        return Path(settings.lfm_models_dir) / filename

    @staticmethod
    def _run_completion(llm: Llama, prompt: str, format: str | None) -> str:
        kwargs = {}
        if format == "json":
            # NOTE: confirm the correct structured-output kwarg against the
            # installed llama-cpp-python version before finalizing — this API
            # has changed across releases (response_format / grammar, etc.)
            kwargs["response_format"] = {"type": "json_object"}
        result = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return result["choices"][0]["message"]["content"]


llama_cpp_provider = LlamaCppProvider()
```

## Classification registry

**New file:** `backend/app/shared/analysis_engine_registry.py`

```python
from app.shared.llm.llama_cpp_provider import llama_cpp_provider
from app.shared.llm.ollama_provider import ollama_provider
from app.shared.llm.provider import LlmProvider

_SPACY_MODELS = {"nl_core_news_lg"}

_LLAMA_CPP_MODELS: dict[str, str] = {
    # repo_id -> GGUF filename
    "LiquidAI/LFM2-1.2B-Extract-GGUF": "LFM2-1.2B-Extract-Q4_K_M.gguf",
    "LiquidAI/LFM2-2.6B-GGUF": "LFM2-2.6B-Q4_K_M.gguf",
}

_PROVIDERS: dict[str, LlmProvider] = {
    "ollama": ollama_provider,
    "llama_cpp": llama_cpp_provider,
}


def classify_ner_engine(model: str) -> str:
    if model in _SPACY_MODELS:
        return "spacy"
    if model in _LLAMA_CPP_MODELS:
        return "llama_cpp"
    return "ollama"


def classify_llm_engine(model: str) -> str:
    if model in _LLAMA_CPP_MODELS:
        return "llama_cpp"
    return "ollama"


def get_llm_provider(engine_kind: str) -> LlmProvider:
    provider = _PROVIDERS.get(engine_kind)
    if provider is None:
        raise ValueError(f"Unknown LLM engine kind: {engine_kind}")
    return provider
```

Confirm the exact GGUF filenames against what's actually published under each repo on Hugging Face before finalizing — the `Q4_K_M` naming convention is typical but should be verified per model, not assumed.

## ner_llm_engine.py — signature change

**File:** `backend/app/create_ner_for_archive/ner_llm_engine.py` (modify existing, added in the earlier NER-via-Ollama context)

```python
# before
from app.shared.ollama_client import generate
...
async def run_ner_llm(text: str, model: str) -> dict:
    raw_response = await generate(model, _ner_prompt(text), format="json")
    ...

# after
from app.shared.llm.provider import LlmProvider
...
async def run_ner_llm(text: str, model: str, provider: LlmProvider) -> dict:
    raw_response = await provider.generate(model, _ner_prompt(text), format="json")
    ...
```

Everything else in this file (prompt text, parsing, dedup, count computation) is unchanged.

## CreateNerForArchive — three-way dispatch

**File:** `backend/app/create_ner_for_archive/create_ner_for_archive.py`

```python
# before
from app.shared.ollama_client import OllamaUnavailableError
_SPACY_MODELS = {"nl_core_news_lg"}
...
if model in _SPACY_MODELS:
    ner_result = await asyncio.to_thread(run_ner, text, model)
else:
    ner_result = await run_ner_llm(text[:settings.ner_llm_char_limit], model)
```

```python
# after
from app.shared.analysis_engine_registry import classify_ner_engine, get_llm_provider
from app.shared.llm.provider import LlmProviderUnavailableError
# (remove the local _SPACY_MODELS constant — now lives in analysis_engine_registry)
...
engine_kind = classify_ner_engine(model)
if engine_kind == "spacy":
    ner_result = await asyncio.to_thread(run_ner, text, model)
else:
    provider = get_llm_provider(engine_kind)
    ner_result = await run_ner_llm(text[:settings.ner_llm_char_limit], model, provider)
```

And the exception handling around this block changes from catching `OllamaUnavailableError` to catching `LlmProviderUnavailableError` (same abort-the-run behavior, provider-agnostic now).

## CreateTopicDetectionForArchive — provider resolution

**File:** `backend/app/create_topic_detection_for_archive/create_topic_detection_for_archive.py`

```python
# before
from app.shared.ollama_client import OllamaUnavailableError, generate
...
raw_response = await generate(model, _topic_prompt(text), format="json")
```

```python
# after
from app.shared.analysis_engine_registry import classify_llm_engine, get_llm_provider
from app.shared.llm.provider import LlmProviderUnavailableError
...
provider = get_llm_provider(classify_llm_engine(model))
raw_response = await provider.generate(model, _topic_prompt(text), format="json")
```

Exception handling changes from `OllamaUnavailableError` to `LlmProviderUnavailableError`, same abort semantics.

## CreateSummariesForArchive — same pattern (verify against actual code first)

Apply the identical change shown above for topic detection. This file's current contents weren't available in this conversation — confirm its actual structure before applying, but the shape of the change (resolve provider via registry, call `provider.generate()`, catch `LlmProviderUnavailableError`) should be the same.

## docker-compose changes

**Files:** `docker-compose.yml`, `docker-compose.prod.yml`

Add a new named volume and mount it into the backend service:

```yaml
volumes:
  llm_models_data:
    # (alongside the existing ollama_data volume declaration)

services:
  backend:
    volumes:
      - llm_models_data:/app/models/lfm
```

## config.py — new setting

**File:** `backend/app/config.py`

```python
lfm_models_dir: str = "/app/models/lfm"
```

## No changes needed

- **`ollama_client.py`** — untouched; `OllamaProvider` wraps it without modification
- **`ner_engine.py` (spaCy)** — untouched
- **Prompt text** (`_ner_prompt`, `_topic_prompt`, summary's prompt) — unchanged; providers are prompt-agnostic
- **`NerRepository`, `TopicDetectionRepository`, `SummaryRepository`** — untouched; both providers still ultimately produce the same result shapes these expect
- **Database / migrations** — none; see "Deferred Work" above
- **Frontend** — not affected; no model choice is exposed by this feature