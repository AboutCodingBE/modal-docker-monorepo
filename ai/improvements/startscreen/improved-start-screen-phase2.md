# Use Case

Extend the startup dashboard from iteration 1 with two new phases: pulling Docker images with per-image progress, and starting services with health monitoring and error reporting. After iteration 1's prerequisite checks pass, the dashboard now shows exactly which images are being downloaded, whether they're cached, and which services are starting up. If a service fails, the user sees the actual container logs — not a generic error.

This iteration replaces the existing `docker compose up` logic in the agent with a controlled, observable startup managed by the orchestrator.

The input of this use case:
Iteration 1 completes successfully (all 5 prerequisite phases pass). No additional user input needed.

Input mechanism of this use case:
The orchestrator automatically continues into phase 6 and 7 after iteration 1's phases succeed.

The output of this feature:
Two additional phases in the startup dashboard with sub-steps showing individual image and service status. On success, all Docker services are running and healthy. On failure, the user sees which service failed and why (container log output), and can relaunch the agent after fixing the issue.

Example status response showing phase 6 in progress:
```json
{
  "current_phase": "pull_images",
  "phases": [
    { "id": "docker_installed", "label": "Docker geïnstalleerd", "status": "success", "detail": "Docker 28.1.0" },
    { "id": "docker_version", "label": "Docker Compose compatibel", "status": "success", "detail": "Docker Compose v2.30.0" },
    { "id": "docker_running", "label": "Docker actief", "status": "success", "detail": "Docker daemon actief" },
    { "id": "cleanup", "label": "Vorige sessie opruimen", "status": "success", "detail": "Geen actieve sessie gevonden" },
    { "id": "port_check", "label": "Poorten beschikbaar", "status": "success", "detail": null },
    {
      "id": "pull_images",
      "label": "Docker images downloaden",
      "status": "running",
      "detail": "3 van 5 images gereed",
      "sub_steps": [
        { "name": "postgres:16-alpine", "status": "success", "detail": "Al beschikbaar" },
        { "name": "apache/tika:3.3.0-full", "status": "success", "detail": "Al beschikbaar" },
        { "name": "archive-app-backend:latest", "status": "success", "detail": "Gedownload" },
        { "name": "archive-app-frontend:latest", "status": "running", "detail": "Downloaden..." },
        { "name": "ollama/ollama:0.23.0", "status": "pending", "detail": null }
      ]
    },
    {
      "id": "start_services",
      "label": "Services opstarten",
      "status": "pending",
      "detail": null
    }
  ]
}
```

Example failure response for service startup:
```json
{
  "current_phase": "start_services",
  "phases": [
    { "id": "docker_installed", "label": "Docker geïnstalleerd", "status": "success", "detail": "Docker 28.1.0" },
    { "id": "docker_version", "label": "Docker Compose compatibel", "status": "success", "detail": "Docker Compose v2.30.0" },
    { "id": "docker_running", "label": "Docker actief", "status": "success", "detail": "Docker daemon actief" },
    { "id": "cleanup", "label": "Vorige sessie opruimen", "status": "success", "detail": "Geen actieve sessie gevonden" },
    { "id": "port_check", "label": "Poorten beschikbaar", "status": "success", "detail": null },
    { "id": "pull_images", "label": "Docker images downloaden", "status": "success", "detail": "5 van 5 images gereed" },
    {
      "id": "start_services",
      "label": "Services opstarten",
      "status": "failed",
      "detail": "Backend kon niet worden gestart. Controleer de logs hieronder en start de applicatie opnieuw.",
      "sub_steps": [
        { "name": "Database (PostgreSQL)", "status": "success", "detail": "Gezond" },
        { "name": "Tika (tekstextractie)", "status": "success", "detail": "Gezond" },
        { "name": "Ollama (AI engine)", "status": "success", "detail": "Gezond" },
        {
          "name": "Backend (API)",
          "status": "failed",
          "detail": "Niet gezond na 120 seconden",
          "logs": "sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection refused\n  Is the server running on host \"db\" (172.18.0.2) and accepting TCP/IP connections on port 5432?"
        },
        { "name": "Frontend (webinterface)", "status": "pending", "detail": null }
      ]
    }
  ]
}
```

# Business Rules

## General
- Same rules as iteration 1: sequential execution, stop on failure, Dutch UI, English logs.
- On failure, show actionable error details (including container logs for service failures). The user fixes the issue and relaunches the agent. No retry button — a fresh restart handles all partial state gracefully.
- Sub-steps within a phase are shown as expandable/collapsible rows under the parent phase.
- First-time user detection: if more than 2 images need downloading in phase 6, show a message: "Dit is de eerste keer dat u de applicatie start. Het downloaden kan enkele minuten duren, afhankelijk van uw internetverbinding."

## Phase 6: Pull Docker images (`pull_images`)

### Image list
Pull these images in order:
1. `postgres:16-alpine`
2. `apache/tika:3.3.0-full` (or whatever pinned version is in docker-compose.prod.yml)
3. `ollama/ollama:0.23.0`
4. `ghcr.io/aboutcodingbe/archive-app-backend:latest`
5. `ghcr.io/aboutcodingbe/archive-app-frontend:latest`

Order rationale: infrastructure images first (smaller, likely cached), app images last (more likely to need updating).

### Pull strategy
- Pull images one by one using `docker pull <image>` (NOT `docker compose pull`) so we can report per-image progress.
- For each image, run `docker pull` and capture stdout/stderr.
- Parse the output to determine:
    - "Already up to date" or "Image is up to date" → status: success, detail: "Al beschikbaar"
    - Layer download output → status: running, detail: "Downloaden..."
    - Successful pull completed → status: success, detail: "Gedownload"
    - Error → status: failed, detail: the error message
- Update the sub-step status in real-time via the SSE stream as each image completes.

### Failure handling
- If an image pull fails (network error, auth error, image not found): FAIL the phase.
- Show the Docker error message in the failed sub-step's detail.
- Common errors and messages:
    - Network unreachable: "Geen internetverbinding. Controleer uw netwerkverbinding en start de applicatie opnieuw."
    - Image not found: "Image niet gevonden. Neem contact op met de beheerder."
    - Auth error for ghcr.io: "Toegang geweigerd. Neem contact op met de beheerder."

### Progress reporting
- After each image completes (success or cached), update the parent phase detail: "X van 5 images gereed"

### Idempotency on relaunch
- `docker pull` is idempotent — already downloaded layers are cached. If the user relaunches after a failed pull, previously downloaded images and layers are reused automatically.

### `--pull always` behavior
- For the backend and frontend images (`:latest` tag), always pull even if cached to ensure the latest version. `docker pull` does this by default.

## Phase 7: Start services (`start_services`)

### Service start order
Start services in dependency order:
1. **Database (PostgreSQL)** — no dependencies
2. **Tika (tekstextractie)** — no dependencies
3. **Ollama (AI engine)** — no dependencies
4. **Backend (API)** — depends on database and Tika being healthy
5. **Frontend (webinterface)** — depends on backend being healthy

### Start strategy
- Do NOT use `docker compose up -d` for all services at once. Start each service individually with `docker compose -f <compose_file> up -d <service_name>` so we can control the order and monitor each one.
- Do NOT start the `ollama-init` service — model pulling is handled in iteration 3's phase 8. If `ollama-init` still exists in docker-compose.prod.yml at this point, exclude it.
- After starting each service, poll its health until it's ready or timeout is reached.

### Health checking per service

**Database (db):**
- Method: `docker inspect --format='{{.State.Health.Status}}' <container_name>`
- The database has a healthcheck defined in docker-compose (pg_isready)
- Wait for status `healthy`
- Timeout: 60 seconds
- Poll interval: 3 seconds

**Tika:**
- Method: HTTP request to `http://localhost:7777/version`
- Tika has no Docker healthcheck — the agent polls directly
- Wait for a 200 response
- Timeout: 120 seconds (Tika is slow to start)
- Poll interval: 5 seconds

**Ollama:**
- Method: HTTP request to `http://localhost:11434/api/tags`
- Wait for a 200 response
- Timeout: 60 seconds
- Poll interval: 3 seconds

**Backend:**
- Method: `docker inspect --format='{{.State.Health.Status}}' <container_name>`
- The backend has a healthcheck defined in docker-compose (curl to /api/health)
- Wait for status `healthy`
- Timeout: 120 seconds (backend waits for DB migrations, Tika, etc.)
- Poll interval: 5 seconds

**Frontend:**
- Method: HTTP request to `http://localhost:4210` (through the agent, to avoid CORS)
- Or: `docker inspect --format='{{.State.Health.Status}}' <container_name>` if frontend has a healthcheck
- Wait for a 200 response
- Timeout: 60 seconds
- Poll interval: 3 seconds

### Sub-step status updates
- When starting a service: sub-step status = "running", detail = "Opstarten..."
- While polling health: detail = "Wachten op gezondheidscontrole..."
- When healthy: status = "success", detail = "Gezond"
- When timeout reached: status = "failed", detail = "Niet gezond na X seconden"

### Failure handling
- If a service fails to become healthy within its timeout: FAIL the phase
- Fetch the last 50 lines of that service's logs: `docker compose -f <compose_file> logs <service_name> --tail 50`
- Store the relevant log lines in the sub-step's `logs` field
- Show the logs to the user in a scrollable monospace/code box
- Do NOT attempt to start subsequent services if a dependency fails (e.g., don't start backend if database failed)
- Add message: "Controleer de logs en start de applicatie opnieuw."

### Idempotency on relaunch
- Phase 4 (cleanup) in iteration 1 ensures all previous containers are stopped before phase 7 runs. So a relaunch always starts services from a clean state.

### Container name resolution
- Use `docker compose -f <compose_file> ps --format json` to map service names to container names/IDs
- Or use the project name convention: `<project>-<service>-1`

## After phases 6 and 7 pass
- All services are running and healthy
- For now (until iteration 3), show "Services zijn opgestart!" and redirect to the app after 2 seconds
- In iteration 3, the orchestrator will continue to phase 8 (AI model pull) before redirecting

# Component Overview

## Changes to StartupOrchestrator

**File:** `agent/startup.py`

Add two new phases to the orchestrator's phase list:

```python
self.state = StartupState(phases=[
    # Iteration 1 phases (unchanged)
    PhaseState(id="docker_installed", label="Docker geïnstalleerd"),
    PhaseState(id="docker_version", label="Docker Compose compatibel"),
    PhaseState(id="docker_running", label="Docker actief"),
    PhaseState(id="cleanup", label="Vorige sessie opruimen"),
    PhaseState(id="port_check", label="Poorten beschikbaar"),
    # Iteration 2 phases (new)
    PhaseState(id="pull_images", label="Docker images downloaden"),
    PhaseState(id="start_services", label="Services opstarten"),
])

self._phases = [
    # Iteration 1 (unchanged)
    DockerInstalledCheck(),
    DockerVersionCheck(),
    DockerRunningCheck(),
    CleanupPhase(compose_file),
    PortCheckPhase(ports=[4210, 8010, 7777, 5442, 11434]),
    # Iteration 2 (new)
    PullImagesPhase(compose_file),
    StartServicesPhase(compose_file),
]
```

### PhaseState extension for sub-steps

Add `sub_steps` support to `PhaseState`:

```python
@dataclass
class SubStep:
    name: str
    status: PhaseStatus = PhaseStatus.PENDING
    detail: str | None = None
    logs: str | None = None

@dataclass
class PhaseState:
    id: str
    label: str
    status: PhaseStatus = PhaseStatus.PENDING
    detail: str | None = None
    errors: list[dict] | None = None
    sub_steps: list[SubStep] | None = None  # NEW
```

The orchestrator must call `_notify()` whenever a sub-step updates so the SSE stream pushes the change.

This component depends on:
- PullImagesPhase
- StartServicesPhase

## PullImagesPhase

**New file or add to:** `agent/startup.py` (or `agent/phases/pull_images.py`)

```python
class PullImagesPhase(StartupPhase):
    IMAGES = [
        ("postgres:16-alpine", "Database (PostgreSQL)"),
        ("apache/tika:3.3.0-full", "Tika (tekstextractie)"),
        ("ollama/ollama:0.23.0", "Ollama (AI engine)"),
        ("ghcr.io/aboutcodingbe/archive-app-backend:latest", "Backend (API)"),
        ("ghcr.io/aboutcodingbe/archive-app-frontend:latest", "Frontend (webinterface)"),
    ]

    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self, phase_state: PhaseState, notify: callable) -> PhaseResult:
        # Initialize sub-steps
        phase_state.sub_steps = [
            SubStep(name=display_name) for _, display_name in self.IMAGES
        ]
        notify()

        completed = 0
        needs_download = 0

        for i, (image, display_name) in enumerate(self.IMAGES):
            sub = phase_state.sub_steps[i]
            sub.status = PhaseStatus.RUNNING
            sub.detail = "Controleren..."
            notify()

            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "pull", image,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                output = stdout.decode() + stderr.decode()

                if proc.returncode != 0:
                    sub.status = PhaseStatus.FAILED
                    sub.detail = self._parse_error(output)
                    notify()
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail=f"Fout bij downloaden van {display_name}. Start de applicatie opnieuw na het oplossen van het probleem.",
                    )

                if "up to date" in output.lower():
                    sub.status = PhaseStatus.SUCCESS
                    sub.detail = "Al beschikbaar"
                else:
                    sub.status = PhaseStatus.SUCCESS
                    sub.detail = "Gedownload"
                    needs_download += 1

                completed += 1
                phase_state.detail = f"{completed} van {len(self.IMAGES)} images gereed"
                notify()

            except Exception as e:
                sub.status = PhaseStatus.FAILED
                sub.detail = str(e)
                notify()
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"Fout bij downloaden van {display_name}. Start de applicatie opnieuw na het oplossen van het probleem.",
                )

        # First-time user detection
        first_time_msg = ""
        if needs_download > 2:
            first_time_msg = " (eerste keer opstarten — dit is eenmalig)"

        return PhaseResult(
            status=PhaseStatus.SUCCESS,
            detail=f"{completed} van {len(self.IMAGES)} images gereed{first_time_msg}",
        )

    def _parse_error(self, output: str) -> str:
        if "not found" in output.lower():
            return "Image niet gevonden. Neem contact op met de beheerder."
        if "unauthorized" in output.lower() or "denied" in output.lower():
            return "Toegang geweigerd. Neem contact op met de beheerder."
        if "network" in output.lower() or "timeout" in output.lower():
            return "Geen internetverbinding. Controleer uw netwerkverbinding en start de applicatie opnieuw."
        return output.strip()[-200:]  # Last 200 chars of output
```

**Note on execute signature:** The phase now receives `phase_state` and `notify` so it can update sub-steps in real-time. The orchestrator needs to pass these in. Adjust the `StartupPhase` interface and orchestrator's run loop accordingly:

```python
# In orchestrator run loop:
result = await phase.execute(phase_state, self._notify)
```

This component depends on:
- `asyncio`
- Docker CLI

## StartServicesPhase

**New file or add to:** `agent/startup.py` (or `agent/phases/start_services.py`)

```python
@dataclass
class ServiceDef:
    compose_name: str        # Service name in docker-compose.yml
    display_name: str        # Dutch display name
    health_method: str       # "docker_health" or "http"
    health_url: str | None   # URL for HTTP health check
    timeout: int             # Seconds to wait for healthy
    poll_interval: int       # Seconds between health checks
    depends_on: list[str]    # List of compose_name dependencies

class StartServicesPhase(StartupPhase):
    SERVICES = [
        ServiceDef(
            compose_name="db",
            display_name="Database (PostgreSQL)",
            health_method="docker_health",
            health_url=None,
            timeout=60,
            poll_interval=3,
            depends_on=[],
        ),
        ServiceDef(
            compose_name="tika",
            display_name="Tika (tekstextractie)",
            health_method="http",
            health_url="http://localhost:7777/version",
            timeout=120,
            poll_interval=5,
            depends_on=[],
        ),
        ServiceDef(
            compose_name="ollama",
            display_name="Ollama (AI engine)",
            health_method="http",
            health_url="http://localhost:11434/api/tags",
            timeout=60,
            poll_interval=3,
            depends_on=[],
        ),
        ServiceDef(
            compose_name="backend",
            display_name="Backend (API)",
            health_method="docker_health",
            health_url=None,
            timeout=120,
            poll_interval=5,
            depends_on=["db", "tika"],
        ),
        ServiceDef(
            compose_name="frontend",
            display_name="Frontend (webinterface)",
            health_method="http",
            health_url="http://localhost:4210",
            timeout=60,
            poll_interval=3,
            depends_on=["backend"],
        ),
    ]

    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self, phase_state: PhaseState, notify: callable) -> PhaseResult:
        # Initialize sub-steps
        phase_state.sub_steps = [
            SubStep(name=svc.display_name) for svc in self.SERVICES
        ]
        notify()

        for i, svc in enumerate(self.SERVICES):
            sub = phase_state.sub_steps[i]

            # Check dependencies
            for dep_name in svc.depends_on:
                dep_index = next(
                    j for j, s in enumerate(self.SERVICES) if s.compose_name == dep_name
                )
                dep_sub = phase_state.sub_steps[dep_index]
                if dep_sub.status == PhaseStatus.FAILED:
                    sub.status = PhaseStatus.FAILED
                    sub.detail = f"Overgeslagen: {self.SERVICES[dep_index].display_name} is niet beschikbaar"
                    notify()
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail=f"{svc.display_name} kon niet worden gestart. Start de applicatie opnieuw na het oplossen van het probleem.",
                    )

            # Start the service
            sub.status = PhaseStatus.RUNNING
            sub.detail = "Opstarten..."
            notify()

            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file, "up", "-d", svc.compose_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                sub.status = PhaseStatus.FAILED
                sub.detail = f"Kon niet worden gestart: {stderr.decode().strip()[-200:]}"
                notify()
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"{svc.display_name} kon niet worden gestart. Start de applicatie opnieuw na het oplossen van het probleem.",
                )

            # Wait for health
            sub.detail = "Wachten op gezondheidscontrole..."
            notify()

            healthy = await self._wait_for_health(svc)

            if healthy:
                sub.status = PhaseStatus.SUCCESS
                sub.detail = "Gezond"
                notify()
            else:
                sub.status = PhaseStatus.FAILED
                sub.detail = f"Niet gezond na {svc.timeout} seconden"
                sub.logs = await self._fetch_logs(svc.compose_name)
                notify()
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"{svc.display_name} kon niet worden gestart. Controleer de logs hieronder en start de applicatie opnieuw.",
                )

        return PhaseResult(
            status=PhaseStatus.SUCCESS,
            detail="Alle services zijn actief",
        )

    async def _wait_for_health(self, svc: ServiceDef) -> bool:
        """Poll health until success or timeout."""
        elapsed = 0
        while elapsed < svc.timeout:
            if svc.health_method == "docker_health":
                if await self._check_docker_health(svc.compose_name):
                    return True
            elif svc.health_method == "http":
                if await self._check_http_health(svc.health_url):
                    return True
            await asyncio.sleep(svc.poll_interval)
            elapsed += svc.poll_interval
        return False

    async def _check_docker_health(self, service_name: str) -> bool:
        """Check Docker health status via docker inspect."""
        # Get container ID first
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", self.compose_file, "ps", "-q", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        container_id = stdout.decode().strip()
        if not container_id:
            return False

        proc2 = await asyncio.create_subprocess_exec(
            "docker", "inspect", "--format", "{{.State.Health.Status}}", container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        return stdout2.decode().strip() == "healthy"

    async def _check_http_health(self, url: str) -> bool:
        """Check health via HTTP GET."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)
                return resp.status_code == 200
        except Exception:
            return False

    async def _fetch_logs(self, service_name: str) -> str:
        """Fetch last 50 lines of service logs."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", self.compose_file,
            "logs", service_name, "--tail", "50",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (stdout.decode() + stderr.decode()).strip()[-2000:]  # Cap at 2000 chars
```

This component depends on:
- `asyncio`
- `httpx` (for HTTP health checks)
- Docker CLI

## Dashboard HTML Updates

**File:** `agent/templates/startup.html`

Extend the dashboard from iteration 1 to support sub-steps:

- Phases with `sub_steps` show a collapsible section under the phase row
- Each sub-step is an indented row with its own status icon, name, and detail
- Sub-steps with `logs` show a scrollable monospace code box (max height ~200px, dark background)
- The logs box has a "Kopiëren" button to copy log content to clipboard
- During image download, if first-time user detection triggers (>2 images downloading), show an info banner above the phase: "Dit is de eerste keer dat u de applicatie start. Het downloaden kan enkele minuten duren, afhankelijk van uw internetverbinding."
- After all phases pass: show success banner "Services zijn opgestart!" and auto-redirect to `http://localhost:4210` after 2 seconds. Also show a manual link: "Klik hier als u niet automatisch wordt doorgestuurd."

This component depends on:
- SSE stream for real-time sub-step updates
- Same design system as iteration 1

## StartupPhase Interface Update

The execute method signature changes to receive the phase state and notify callback, allowing phases to update sub-steps in real-time:

```python
class StartupPhase:
    async def execute(self, phase_state: PhaseState, notify: callable) -> PhaseResult:
        raise NotImplementedError
```

Update iteration 1's phases to accept the new signature (they can ignore phase_state and notify since they don't use sub-steps). Or use default parameters for backward compatibility:

```python
# Iteration 1 phases can keep working with:
async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
    ...
```

This component depends on:
- Nothing new

## Remove existing startup logic

**File:** `agent/agent.py`

The existing startup logic that runs `docker compose up -d` and polls for readiness should be removed or bypassed — the orchestrator's phase 7 now handles this entirely. The agent should:

1. Start Flask
2. Open browser
3. Run orchestrator (phases 1-7)
4. If all phases pass: the app is ready, redirect to frontend
5. The existing `/health/backend` proxy endpoint and other agent endpoints remain unchanged

This component depends on:
- StartupOrchestrator

# Wireframe

For the visual design of the startup dashboard, refer to the wireframe at: `[PLACEHOLDER_WIREFRAME_LOCATION]`

# Testing Notes

- Test with no images cached (first-time user): all 5 images should download, first-time message should appear
- Test with all images cached: all sub-steps should show "Al beschikbaar" quickly
- Test with some images cached, some needing update (e.g. new backend image pushed)
- Test image pull with network disconnected: should fail with meaningful error
- Test service startup with database healthy: backend should wait and eventually succeed
- Test service startup with Tika slow to start (normal behavior): dashboard should show "Wachten op gezondheidscontrole..." patiently until Tika responds
- Test service startup with backend failing (e.g. wrong DATABASE_URL): should show container logs
- Test that `ollama-init` is NOT started (even if still in docker-compose.prod.yml)
- Verify sub-steps expand/collapse correctly in the dashboard
- Verify logs are readable and the copy button works
- Test a full relaunch after a service startup failure — phase 4 cleans up leftover containers, phase 6 reuses cached images, phase 7 starts fresh