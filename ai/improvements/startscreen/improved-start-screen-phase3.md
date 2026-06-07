# Use Case

Complete the startup dashboard with the final two phases: pulling the AI model from Ollama with download progress, and the ready phase that redirects to the app. This iteration also removes the `ollama-init` service from docker-compose (the agent now owns model management) and adds first-time user messaging during model download.

The input of this use case:
Iteration 2 completes successfully (all 7 phases pass, all services running and healthy). No additional user input needed.

Input mechanism of this use case:
The orchestrator automatically continues into phase 8 and 9 after iteration 2's phases succeed.

The output of this feature:
Two final phases in the startup dashboard. Phase 8 shows AI model download progress with MB and percentage. Phase 9 confirms everything is ready and redirects to the app. The full startup sequence is now: prerequisites → images → services → AI model → ready.

Example status response showing phase 8 in progress:
```json
{
  "current_phase": "pull_ai_model",
  "phases": [
    { "id": "docker_installed", "label": "Docker geïnstalleerd", "status": "success", "detail": "Docker 28.1.0" },
    { "id": "docker_version", "label": "Docker Compose compatibel", "status": "success", "detail": "Docker Compose v2.30.0" },
    { "id": "docker_running", "label": "Docker actief", "status": "success", "detail": "Docker daemon actief" },
    { "id": "cleanup", "label": "Vorige sessie opruimen", "status": "success", "detail": "Geen actieve sessie gevonden" },
    { "id": "port_check", "label": "Poorten beschikbaar", "status": "success", "detail": null },
    { "id": "pull_images", "label": "Docker images downloaden", "status": "success", "detail": "5 van 5 images gereed" },
    { "id": "start_services", "label": "Services opstarten", "status": "success", "detail": "Alle services zijn actief" },
    {
      "id": "pull_ai_model",
      "label": "AI model downloaden",
      "status": "running",
      "detail": "gemma3:1b — 340 MB / 815 MB (42%)"
    },
    {
      "id": "ready",
      "label": "Applicatie gereed",
      "status": "pending",
      "detail": null
    }
  ]
}
```

Example status when model is already available:
```json
{
  "id": "pull_ai_model",
  "label": "AI model downloaden",
  "status": "success",
  "detail": "Model gemma3:1b al beschikbaar"
}
```

Example status when ready:
```json
{
  "id": "ready",
  "label": "Applicatie gereed",
  "status": "success",
  "detail": "Doorsturen naar applicatie...",
  "redirect_url": "http://localhost:4210"
}
```

# Business Rules

## General
- Same rules as iteration 1 and 2: sequential execution, stop on failure, Dutch UI, English logs.
- On failure, show actionable error details. The user fixes the issue and relaunches the agent. No retry button — every phase is idempotent, so a fresh restart handles all partial state gracefully (cached images reused, partially downloaded models resumed, leftover containers cleaned up).

## Phase 8: Pull AI model (`pull_ai_model`)

### Check if model exists
- Before pulling, check if the model is already available
- `GET http://localhost:11434/api/tags`
- Response contains a `models` array. Check if any model's `name` field matches `gemma3:1b` (or starts with `gemma3:1b`)
- If model exists: SUCCESS with detail "Model gemma3:1b al beschikbaar"
- If model does not exist: proceed to pull

### Pull with streaming progress
- `POST http://localhost:11434/api/pull` with body `{"name": "gemma3:1b", "stream": true}`
- Response is NDJSON (newline-delimited JSON). Each line is a progress update:
  ```json
  {"status": "pulling manifest"}
  {"status": "pulling abc123", "digest": "sha256:abc123", "total": 815000000, "completed": 340000000}
  {"status": "pulling abc123", "digest": "sha256:abc123", "total": 815000000, "completed": 815000000}
  {"status": "verifying sha256 digest"}
  {"status": "writing manifest"}
  {"status": "success"}
  ```
- Parse each line and update the phase detail with download progress
- Format progress as: "gemma3:1b — X MB / Y MB (Z%)"
    - Convert bytes to MB: `completed / 1_000_000` rounded to nearest integer
    - Calculate percentage: `(completed / total) * 100` rounded to nearest integer
- Push updates via SSE/notify on each progress line (throttle to max once per second to avoid flooding)
- The final line will have `"status": "success"` — mark the phase as SUCCESS

### Timeout
- Total timeout for model pull: 600 seconds (10 minutes)
- The model is roughly 800MB-1.2GB depending on version
- If timeout is reached: FAIL with detail "Het downloaden van het AI model duurde te lang. Controleer uw internetverbinding en start de applicatie opnieuw."

### Error handling
- If the Ollama API is unreachable (connection refused): FAIL with detail "Ollama service is niet bereikbaar. Start de applicatie opnieuw."
- If the response contains an `error` field: FAIL with the error message
    - Example: `{"error": "pull model manifest: file does not exist"}` → "Model gemma3:1b kon niet worden gevonden. Neem contact op met de beheerder."
- If the stream disconnects mid-download: FAIL with detail "Verbinding verbroken tijdens downloaden. Controleer uw internetverbinding en start de applicatie opnieuw."

### First-time user messaging
- If the model needs downloading (not already cached), show an info message on the dashboard: "Het AI model wordt gedownload. Dit is eenmalig en kan even duren."

### Idempotency on relaunch
- Ollama persists partial downloads in its volume. If the user relaunches after a failed model pull, Ollama's pull API resumes where it left off automatically.

### Model name configuration
- The model name (`gemma3:1b`) should come from a central configuration, not hardcoded in the phase
- Use the agent's `config.json` or read from docker-compose.prod.yml
- For now, default to `gemma3:1b` if no configuration is found
- This allows changing the model later without modifying the startup code

## Phase 9: Ready (`ready`)

### Final verification
- Before declaring ready, do one final check that all critical services respond:
    - Backend health: `GET http://localhost:8010/api/health` returns 200
    - Frontend accessible: `GET http://localhost:4210` returns 200
- If any check fails: FAIL with detail about which service is no longer responding (it may have crashed after startup). Message: "Start de applicatie opnieuw."
- If all checks pass: SUCCESS

### Redirect
- Mark phase as SUCCESS with detail "Doorsturen naar applicatie..."
- Include `redirect_url` in the phase state: `http://localhost:4210`
- The dashboard JavaScript detects the `redirect_url` field and triggers a redirect after 2 seconds
- Also show a clickable link below: "Klik hier als u niet automatisch wordt doorgestuurd." pointing to `redirect_url`

### Completion logging
- Log the total startup time: "Startup completed in X seconds"
- Log which phases were fast (cached images, model already available) vs slow (fresh downloads)

# Component Overview

## PullAIModelPhase

**New file or add to:** `agent/startup.py` (or `agent/phases/pull_ai_model.py`)

```python
import httpx
import json
import asyncio

class PullAIModelPhase(StartupPhase):
    def __init__(self, model: str = "gemma3:1b", ollama_url: str = "http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = 600  # 10 minutes

    async def execute(self, phase_state: PhaseState, notify: callable) -> PhaseResult:
        # Step 1: Check if model already exists
        phase_state.detail = "Controleren of model beschikbaar is..."
        notify()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    for m in models:
                        if m.get("name", "").startswith(self.model):
                            return PhaseResult(
                                status=PhaseStatus.SUCCESS,
                                detail=f"Model {self.model} al beschikbaar",
                            )
        except httpx.ConnectError:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Ollama service is niet bereikbaar. Start de applicatie opnieuw.",
            )
        except Exception as e:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail=f"Fout bij controleren model: {e}",
            )

        # Step 2: Pull model with streaming progress
        phase_state.detail = f"Voorbereiden download {self.model}..."
        notify()

        try:
            last_notify_time = 0

            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                async with client.stream(
                    "POST",
                    f"{self.ollama_url}/api/pull",
                    json={"name": self.model, "stream": True},
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Check for error
                        if "error" in data:
                            return PhaseResult(
                                status=PhaseStatus.FAILED,
                                detail=f"Fout: {data['error']}",
                            )

                        # Check for completion
                        if data.get("status") == "success":
                            return PhaseResult(
                                status=PhaseStatus.SUCCESS,
                                detail=f"Model {self.model} gedownload",
                            )

                        # Update progress
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)

                        if total > 0:
                            total_mb = total // 1_000_000
                            completed_mb = completed // 1_000_000
                            pct = round((completed / total) * 100)
                            phase_state.detail = (
                                f"{self.model} — {completed_mb} MB / {total_mb} MB ({pct}%)"
                            )
                        else:
                            phase_state.detail = f"{data.get('status', 'Bezig...')}"

                        # Throttle notifications to max once per second
                        now = asyncio.get_event_loop().time()
                        if now - last_notify_time >= 1.0:
                            notify()
                            last_notify_time = now

        except httpx.ConnectError:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Ollama service is niet bereikbaar. Start de applicatie opnieuw.",
            )
        except httpx.ReadTimeout:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Het downloaden van het AI model duurde te lang. Controleer uw internetverbinding en start de applicatie opnieuw.",
            )
        except httpx.ReadError:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Verbinding verbroken tijdens downloaden. Controleer uw internetverbinding en start de applicatie opnieuw.",
            )
        except Exception as e:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail=f"Onverwachte fout: {e}",
            )

        # If we get here without success, something went wrong
        return PhaseResult(
            status=PhaseStatus.FAILED,
            detail="Model download onverwacht afgebroken. Start de applicatie opnieuw.",
        )
```

This component depends on:
- `httpx` (async HTTP client with streaming support)
- `asyncio`
- Ollama API running on `http://localhost:11434`

## ReadyPhase

**New file or add to:** `agent/startup.py` (or `agent/phases/ready.py`)

```python
class ReadyPhase(StartupPhase):
    def __init__(self, frontend_url: str = "http://localhost:4210",
                 backend_health_url: str = "http://localhost:8010/api/health"):
        self.frontend_url = frontend_url
        self.backend_health_url = backend_health_url

    async def execute(self, phase_state: PhaseState, notify: callable) -> PhaseResult:
        phase_state.detail = "Laatste controles uitvoeren..."
        notify()

        # Verify backend still responds
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.backend_health_url, timeout=10)
                if resp.status_code != 200:
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail="Backend reageert niet meer. Start de applicatie opnieuw.",
                    )
        except Exception:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Backend is niet bereikbaar. Start de applicatie opnieuw.",
            )

        # Verify frontend still responds
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.frontend_url, timeout=10)
                if resp.status_code != 200:
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail="Frontend reageert niet meer. Start de applicatie opnieuw.",
                    )
        except Exception:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Frontend is niet bereikbaar. Start de applicatie opnieuw.",
            )

        return PhaseResult(
            status=PhaseStatus.SUCCESS,
            detail="Doorsturen naar applicatie...",
            redirect_url=self.frontend_url,
        )
```

**Note:** `PhaseResult` needs a new optional field:

```python
@dataclass
class PhaseResult:
    status: PhaseStatus
    detail: str | None = None
    errors: list[dict] | None = None
    redirect_url: str | None = None  # NEW — signals the dashboard to redirect
```

The orchestrator should copy `redirect_url` to the phase state so it's included in the SSE/JSON response.

This component depends on:
- `httpx`

## Changes to StartupOrchestrator

**File:** `agent/startup.py`

Add the two new phases:

```python
self.state = StartupState(phases=[
    # Iteration 1
    PhaseState(id="docker_installed", label="Docker geïnstalleerd"),
    PhaseState(id="docker_version", label="Docker Compose compatibel"),
    PhaseState(id="docker_running", label="Docker actief"),
    PhaseState(id="cleanup", label="Vorige sessie opruimen"),
    PhaseState(id="port_check", label="Poorten beschikbaar"),
    # Iteration 2
    PhaseState(id="pull_images", label="Docker images downloaden"),
    PhaseState(id="start_services", label="Services opstarten"),
    # Iteration 3
    PhaseState(id="pull_ai_model", label="AI model downloaden"),
    PhaseState(id="ready", label="Applicatie gereed"),
])

self._phases = [
    # Iteration 1
    DockerInstalledCheck(),
    DockerVersionCheck(),
    DockerRunningCheck(),
    CleanupPhase(compose_file),
    PortCheckPhase(ports=[4210, 8010, 7777, 5442, 11434]),
    # Iteration 2
    PullImagesPhase(compose_file),
    StartServicesPhase(compose_file),
    # Iteration 3
    PullAIModelPhase(model=config.get("ai_model", "gemma3:1b"), ollama_url="http://localhost:11434"),
    ReadyPhase(frontend_url=config["frontend_url"]),
]
```

### Startup timing

Add timing to the orchestrator:

```python
import time

async def run(self):
    start_time = time.time()

    # ... existing phase loop ...

    elapsed = time.time() - start_time
    _logger.info(f"Startup completed in {elapsed:.1f} seconds")
    return True
```

## Dashboard HTML Updates

**File:** `agent/templates/startup.html`

### AI model download display
- Phase 8 shows a progress bar when downloading (not just text)
- The progress bar fills based on the percentage from the detail string
- Parse the detail string in JavaScript to extract the percentage, or add a `progress` field to the phase state
- When the model is already cached, no progress bar — just the success checkmark
- Show info banner when model needs downloading: "Het AI model wordt gedownload. Dit is eenmalig en kan even duren."

### Ready phase and redirect
- When phase 9 succeeds and contains `redirect_url`:
    - Show a success banner: "Applicatie is gereed!"
    - Show a countdown: "U wordt doorgestuurd in 2 seconden..."
    - After 2 seconds: `window.location.href = redirect_url`
    - Also show a manual link below: "Klik hier als u niet automatisch wordt doorgestuurd." pointing to `redirect_url`

### Overall completion state
- When all 9 phases are SUCCESS, the entire dashboard gets a subtle success indication
- The phase list stays visible so the user can see everything that was checked

This component depends on:
- SSE stream
- Same design system as iterations 1 and 2

## Docker Compose Changes

### docker-compose.prod.yml

Remove the `ollama-init` service entirely:

```yaml
# REMOVE THIS ENTIRE SERVICE:
  ollama-init:
    image: curlimages/curl:latest
    depends_on:
      ollama:
        condition: service_started
    restart: "no"
    entrypoint: >
      sh -c "
        echo 'Waiting for Ollama to be ready...' &&
        until curl -sf http://ollama:11434/api/tags > /dev/null 2>&1; do
          sleep 2;
        done &&
        echo 'Pulling default model...' &&
        RESULT=$(curl -s -X POST http://ollama:11434/api/pull -d '{\"name\": \"gemma3:1b\"}') &&
        if echo \"$RESULT\" | grep -q error; then
          echo \"ERROR: Model pull failed: $RESULT\" &&
          exit 1;
        else
          echo 'Default model ready.';
        fi
      "
```

This also eliminates:
- The `curlimages/curl:latest` image dependency (one less image to pull)
- The `RESULT` variable warning ("The RESULT variable is not set. Defaulting to a blank string.")

### docker-compose.yml (dev)

Remove `ollama-init` here too if present. In dev mode, when running the agent with `--dev`, the AI model pull phase should use `http://localhost:11434` for the Ollama URL.

## Agent Config Update

**File:** `agent/config.json`

Add the model name to configuration so it's not hardcoded:

```json
{
  "agent_port": 9090,
  "frontend_url": "http://localhost:4210",
  "compose_file": "docker-compose.prod.yml",
  "log_file": "~/.archive-app/agent.log",
  "ai_model": "gemma3:1b"
}
```

The `PullAIModelPhase` reads the model name from this config. If the field is missing, default to `gemma3:1b`.

## Cheat Sheet Updates

Update the project cheat sheet to reflect:
- `ollama-init` service removed from docker-compose
- Agent now handles AI model management
- Startup dashboard replaces the basic loading page
- 9-phase startup sequence documented
- `config.json` now includes `ai_model` field

# Testing Notes

## Phase 8: Pull AI model
- Test with model already downloaded: should show "Model gemma3:1b al beschikbaar" immediately
- Test with model not downloaded: should show streaming progress with MB and percentage
- Test with Ollama not responding: should fail with "Ollama service is niet bereikbaar"
- Test with network disconnection during model download: should fail with meaningful error
- Test with invalid model name in config: should fail with model not found error
- Test that progress updates are throttled (not flooding the SSE stream)
- Verify progress bar fills smoothly in the dashboard
- Test relaunch after failed model pull — Ollama resumes partial download automatically

## Phase 9: Ready
- Test with all services healthy: should show success and redirect
- Test with backend crashed between phase 7 and phase 9: should detect and fail
- Test redirect in different browsers (Chrome, Firefox, Safari)
- Test the manual "Klik hier" link works
- Verify 2-second delay before redirect
- Verify startup time is logged

## Docker Compose
- Verify `ollama-init` is removed and no `RESULT` warnings appear
- Verify `docker compose up -d` no longer tries to start `ollama-init`
- Verify the model is still available after a clean restart (Ollama volume persists)

## End-to-end
- Full cold start (no Docker images, no model): all 9 phases should complete successfully
- Full warm start (everything cached): should complete in under 30 seconds
- Partial state (images cached, model missing): should skip image downloads, pull model
- Relaunch after failure at any phase: phase 4 cleans up containers, subsequent phases handle cached state gracefully
- Verify total startup time is logged