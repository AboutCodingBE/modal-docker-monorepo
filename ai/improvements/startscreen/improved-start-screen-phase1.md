# Use Case

Replace the current basic loading screen with the first iteration of a diagnostic startup dashboard. This iteration covers prerequisite checks and cleanup: verifying Docker is installed, the right version, running, cleaning up leftover containers, and checking port availability. The dashboard gives actionable feedback when something is wrong — not generic errors.

The input of this use case:
User starts the agent (double-click or terminal). No other input needed.

Input mechanism of this use case:
Agent starts, opens browser to the dashboard, and runs the diagnostic phases automatically.

The output of this feature:
A browser-based dashboard showing real-time progress through 5 prerequisite phases. Each phase shows a status (pending/running/success/failed) with a detail message. On failure, the user sees what's wrong and how to fix it, then relaunches the agent after resolving the issue. On success of all 5 phases, the dashboard shows "Voorbereidingen voltooid" and proceeds to start Docker Compose as before (the existing startup logic kicks in after the prerequisites pass).

Example status response from `GET /startup-status`:
```json
{
  "current_phase": "port_check",
  "phases": [
    {
      "id": "docker_installed",
      "label": "Docker geïnstalleerd",
      "status": "success",
      "detail": "Docker 28.1.0"
    },
    {
      "id": "docker_version",
      "label": "Docker Compose compatibel",
      "status": "success",
      "detail": "Docker Compose v2.30.0"
    },
    {
      "id": "docker_running",
      "label": "Docker actief",
      "status": "success",
      "detail": null
    },
    {
      "id": "cleanup",
      "label": "Vorige sessie opruimen",
      "status": "success",
      "detail": "3 containers gestopt"
    },
    {
      "id": "port_check",
      "label": "Poorten beschikbaar",
      "status": "running",
      "detail": "Poorten controleren..."
    }
  ]
}
```

Example failure response:
```json
{
  "current_phase": "port_check",
  "phases": [
    {
      "id": "docker_installed",
      "label": "Docker geïnstalleerd",
      "status": "success",
      "detail": "Docker 28.1.0"
    },
    {
      "id": "docker_version",
      "label": "Docker Compose compatibel",
      "status": "success",
      "detail": "Docker Compose v2.30.0"
    },
    {
      "id": "docker_running",
      "label": "Docker actief",
      "status": "success",
      "detail": null
    },
    {
      "id": "cleanup",
      "label": "Vorige sessie opruimen",
      "status": "success",
      "detail": "Geen actieve sessie gevonden"
    },
    {
      "id": "port_check",
      "label": "Poorten beschikbaar",
      "status": "failed",
      "detail": "Sommige poorten zijn in gebruik",
      "errors": [
        {
          "port": 4210,
          "process": "node",
          "pid": 12345,
          "message": "Poort 4210 is in gebruik door proces 'node' (PID 12345)",
          "fix": "Voer uit in terminal: kill 12345"
        },
        {
          "port": 5442,
          "process": "postgres",
          "pid": 67890,
          "message": "Poort 5442 is in gebruik door proces 'postgres' (PID 67890)",
          "fix": "Voer uit in terminal: kill 67890"
        }
      ]
    }
  ]
}
```

# Business Rules

## General
- Phases execute strictly in order. If a phase fails, the sequence stops.
- All user-facing text is in Dutch.
- All log messages are in English.
- On failure, the dashboard shows the error with actionable remediation instructions. The user fixes the issue and relaunches the agent — there is no retry button. Every phase is idempotent and handles existing state, so a fresh restart is always safe and fast.
- The agent port (9090) is excluded from port checks — the agent is already running on it.

## Phase 1: Docker installed (`docker_installed`)
- Run `docker --version` via subprocess
- If command not found or fails: FAIL
    - Detect OS using `platform.system()`
    - Show install link per OS:
        - macOS: `https://docs.docker.com/desktop/install/mac-install/`
        - Windows: `https://docs.docker.com/desktop/install/windows-install/`
        - Linux: `https://docs.docker.com/engine/install/`
    - Message: "Docker is niet geïnstalleerd. Installeer Docker via de link hieronder en start de applicatie opnieuw."
- If success: parse version from output (e.g. "Docker version 28.1.0, build ..."), show in detail

## Phase 2: Docker Compose version compatible (`docker_version`)
- Run `docker compose version` (NO hyphen — only Compose v2 is supported)
- If command fails: FAIL
    - Message: "Docker Compose v2 is niet beschikbaar. Update Docker naar de laatste versie en start de applicatie opnieuw."
    - Link: `https://docs.docker.com/compose/install/`
- If success: parse version from output, show in detail
- Do NOT check for `docker-compose` (hyphen). It is not supported.

## Phase 3: Docker running (`docker_running`)
- Run `docker info` via subprocess
- If it fails with connection error: FAIL
    - Detect OS for specific guidance:
        - macOS: "Docker is niet actief. Open Docker Desktop vanuit de Applications map en start de applicatie opnieuw."
        - Windows: "Docker is niet actief. Start Docker Desktop vanuit het Start menu en start de applicatie opnieuw."
        - Linux: "Docker is niet actief. Start de Docker daemon met: sudo systemctl start docker — en start de applicatie opnieuw."
- If success: pass, no detail needed (or show "Docker daemon actief")

## Phase 4: Cleanup previous session (`cleanup`)
- Run `docker compose -f <compose_file> ps -q` to find existing containers from our project
- If containers found:
    - Run `docker compose -f <compose_file> down --timeout 10`
    - If `down` doesn't complete within 15 seconds: escalate to `--timeout 0`
    - Count how many containers were stopped
    - Detail: "X containers gestopt"
- If no containers found:
    - Detail: "Geen actieve sessie gevonden"
- This phase always succeeds — even if no containers were found
- Do NOT ask the user for confirmation. Just clean up.

## Phase 5: Port check (`port_check`)
- Ports to check: 4210 (frontend), 8010 (backend), 7777 (Tika), 5442 (Postgres), 11434 (Ollama)
- Do NOT check port 9090 (agent is using it)
- For each port, check if it's in use:
    - macOS/Linux: `lsof -i :<port> -t` to get PID, then `ps -p <pid> -o comm=` to get process name
    - Windows: `netstat -ano | findstr :<port>` to get PID, then `tasklist /FI "PID eq <pid>"` to get process name
- If ANY port is occupied: FAIL
    - Show ALL conflicts at once (not one at a time)
    - Per conflict show: port number, process name, PID, and the kill command
    - macOS/Linux fix: "Voer uit in terminal: kill <PID>"
    - Windows fix: "Voer uit in PowerShell: taskkill /PID <PID> /F"
    - Add general message: "Sluit de processen en start de applicatie opnieuw."
- If all ports are free: SUCCESS

## After all phases pass
- Once all 5 phases succeed, hand off to the existing startup logic (docker compose up, etc.)
- The dashboard stays visible and can later (iteration 2) show the remaining phases
- For now, show "Voorbereidingen voltooid. Services worden opgestart..." and proceed as before

# Component Overview

## Startup Dashboard HTML Page

**New file:** `agent/templates/startup.html`

A single-page HTML/CSS/JS dashboard served by Flask. Replaces the current `loading.html`.

Visual design:
- Match the main app's design system: sidebar color `#1a2744`, primary blue `#3b6ef5`, background `#f0f2f5`
- App title/logo at the top
- Each phase is a row with:
    - Status icon: spinner (running), green checkmark (success), red cross (failed), grey circle (pending)
    - Phase label (Dutch)
    - Detail text (when available)
- Failed phases expand to show:
    - Error message in a red-tinted box
    - Remediation instructions including "start de applicatie opnieuw" guidance
    - Links (if applicable, e.g. Docker install link) — styled as clickable
    - Fix commands in a monospace/code box that the user can copy
- On all phases complete: show a success banner and "Applicatie wordt gestart..." message

Uses SSE (`EventSource` in JavaScript) to receive real-time updates from `/startup-status/stream`. Falls back to polling `/startup-status` every 2 seconds if SSE is not available.

This component depends on:
- `/startup-status` or `/startup-status/stream` endpoint

## SSE Status Stream Endpoint

**Endpoint:** `GET /startup-status/stream`
**Content-Type:** `text/event-stream`

Streams startup state updates as SSE events. Each event is the full state JSON (same structure as the `/startup-status` response). A new event is pushed whenever a phase changes status.

```
data: {"current_phase": "docker_installed", "phases": [...]}

data: {"current_phase": "docker_version", "phases": [...]}
```

This component depends on:
- StartupOrchestrator state

## Status Polling Endpoint (fallback)

**Endpoint:** `GET /startup-status`

Returns the current state as JSON. Same structure as SSE events. Used as fallback if SSE is not available, polled every 2 seconds.

This component depends on:
- StartupOrchestrator state

## StartupOrchestrator

**New file:** `agent/startup.py`

Orchestrates the sequential execution of startup phases. Maintains state.

```python
from dataclasses import dataclass, field
from enum import Enum

class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class PhaseState:
    id: str
    label: str
    status: PhaseStatus = PhaseStatus.PENDING
    detail: str | None = None
    errors: list[dict] | None = None

@dataclass
class StartupState:
    current_phase: str | None = None
    phases: list[PhaseState] = field(default_factory=list)

class StartupOrchestrator:
    def __init__(self, compose_file: str):
        self.compose_file = compose_file
        self.state = StartupState(phases=[
            PhaseState(id="docker_installed", label="Docker geïnstalleerd"),
            PhaseState(id="docker_version", label="Docker Compose compatibel"),
            PhaseState(id="docker_running", label="Docker actief"),
            PhaseState(id="cleanup", label="Vorige sessie opruimen"),
            PhaseState(id="port_check", label="Poorten beschikbaar"),
        ])
        self._phases = [
            DockerInstalledCheck(),
            DockerVersionCheck(),
            DockerRunningCheck(),
            CleanupPhase(compose_file),
            PortCheckPhase(ports=[4210, 8010, 7777, 5442, 11434]),
        ]
        self._on_update = None  # callback for SSE push

    def set_update_callback(self, callback):
        """Set a callback that is called whenever state changes (for SSE)."""
        self._on_update = callback

    async def run(self):
        """Run all phases sequentially. Stops on first failure."""
        for i in range(len(self._phases)):
            phase = self._phases[i]
            phase_state = self.state.phases[i]

            self.state.current_phase = phase_state.id
            phase_state.status = PhaseStatus.RUNNING
            phase_state.detail = None
            phase_state.errors = None
            self._notify()

            result = await phase.execute()

            phase_state.status = result.status
            phase_state.detail = result.detail
            phase_state.errors = result.errors
            self._notify()

            if result.status == PhaseStatus.FAILED:
                return False

        return True

    def get_state_dict(self) -> dict:
        """Serialize state for JSON response."""
        ...

    def _notify(self):
        if self._on_update:
            self._on_update(self.get_state_dict())
```

This component depends on:
- Phase implementations
- asyncio

## Phase Interface

Each phase implements this interface:

```python
@dataclass
class PhaseResult:
    status: PhaseStatus
    detail: str | None = None
    errors: list[dict] | None = None

class StartupPhase:
    async def execute(self) -> PhaseResult:
        raise NotImplementedError
```

## DockerInstalledCheck

Runs `docker --version` via `asyncio.create_subprocess_exec`.

```python
class DockerInstalledCheck(StartupPhase):
    async def execute(self) -> PhaseResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=self._install_message(),
                )
            version = self._parse_version(stdout.decode())
            return PhaseResult(status=PhaseStatus.SUCCESS, detail=version)
        except FileNotFoundError:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail=self._install_message(),
            )

    def _install_message(self) -> str:
        os_name = platform.system()
        links = {
            "Darwin": "https://docs.docker.com/desktop/install/mac-install/",
            "Windows": "https://docs.docker.com/desktop/install/windows-install/",
            "Linux": "https://docs.docker.com/engine/install/",
        }
        link = links.get(os_name, links["Linux"])
        return f"Docker is niet geïnstalleerd. Installeer Docker via {link} en start de applicatie opnieuw."

    def _parse_version(self, output: str) -> str:
        # "Docker version 28.1.0, build ..." → "Docker 28.1.0"
        ...
```

This component depends on:
- `asyncio`
- `platform`

## DockerVersionCheck

Runs `docker compose version`.

```python
class DockerVersionCheck(StartupPhase):
    async def execute(self) -> PhaseResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail="Docker Compose v2 is niet beschikbaar. Update Docker naar de laatste versie en start de applicatie opnieuw.",
                )
            version = stdout.decode().strip()
            return PhaseResult(status=PhaseStatus.SUCCESS, detail=version)
        except FileNotFoundError:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Docker Compose v2 is niet beschikbaar. Update Docker naar de laatste versie en start de applicatie opnieuw.",
            )
```

This component depends on:
- `asyncio`

## DockerRunningCheck

Runs `docker info`.

```python
class DockerRunningCheck(StartupPhase):
    async def execute(self) -> PhaseResult:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail=self._not_running_message(),
            )
        return PhaseResult(status=PhaseStatus.SUCCESS, detail="Docker daemon actief")

    def _not_running_message(self) -> str:
        os_name = platform.system()
        if os_name == "Darwin":
            return "Docker is niet actief. Open Docker Desktop vanuit de Applications map en start de applicatie opnieuw."
        elif os_name == "Windows":
            return "Docker is niet actief. Start Docker Desktop vanuit het Start menu en start de applicatie opnieuw."
        else:
            return "Docker is niet actief. Start de Docker daemon met: sudo systemctl start docker — en start de applicatie opnieuw."
```

This component depends on:
- `asyncio`
- `platform`

## CleanupPhase

Stops any leftover containers from a previous session.

```python
class CleanupPhase(StartupPhase):
    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self) -> PhaseResult:
        # Check for existing containers
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", self.compose_file, "ps", "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        container_ids = stdout.decode().strip().split("\n")
        container_ids = [c for c in container_ids if c]

        if not container_ids:
            return PhaseResult(
                status=PhaseStatus.SUCCESS,
                detail="Geen actieve sessie gevonden",
            )

        count = len(container_ids)

        # Shut down gracefully
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", self.compose_file, "down", "--timeout", "10",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=20)
        except asyncio.TimeoutError:
            # Force kill
            proc.kill()
            proc2 = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file, "down", "--timeout", "0",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc2.communicate()

        return PhaseResult(
            status=PhaseStatus.SUCCESS,
            detail=f"{count} containers gestopt",
        )
```

This component depends on:
- `asyncio`

## PortCheckPhase

Checks if required ports are free. Platform-aware.

```python
class PortCheckPhase(StartupPhase):
    def __init__(self, ports: list[int]):
        self.ports = ports

    async def execute(self) -> PhaseResult:
        conflicts = []
        for port in self.ports:
            info = await self._check_port(port)
            if info:
                conflicts.append(info)

        if conflicts:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Sommige poorten zijn in gebruik. Sluit de processen en start de applicatie opnieuw.",
                errors=conflicts,
            )
        return PhaseResult(status=PhaseStatus.SUCCESS)

    async def _check_port(self, port: int) -> dict | None:
        os_name = platform.system()
        if os_name in ("Darwin", "Linux"):
            return await self._check_port_unix(port)
        elif os_name == "Windows":
            return await self._check_port_windows(port)
        return None

    async def _check_port_unix(self, port: int) -> dict | None:
        proc = await asyncio.create_subprocess_exec(
            "lsof", "-i", f":{port}", "-t",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0 or not stdout.strip():
            return None  # Port is free

        pid = stdout.decode().strip().split("\n")[0]

        # Get process name
        proc2 = await asyncio.create_subprocess_exec(
            "ps", "-p", pid, "-o", "comm=",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        process_name = stdout2.decode().strip() or "onbekend"

        return {
            "port": port,
            "process": process_name,
            "pid": int(pid),
            "message": f"Poort {port} is in gebruik door proces '{process_name}' (PID {pid})",
            "fix": f"Voer uit in terminal: kill {pid}",
        }

    async def _check_port_windows(self, port: int) -> dict | None:
        proc = await asyncio.create_subprocess_exec(
            "netstat", "-ano",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        # Parse output for the port, find PID
        # Then use tasklist to get process name
        # Return conflict dict with fix: "Voer uit in PowerShell: taskkill /PID <PID> /F"
        # Or None if port is free
        ...
```

This component depends on:
- `asyncio`
- `platform`

## Agent Entry Point Changes

**File:** `agent/agent.py`

- Replace the current loading page with the new startup dashboard
- Change the `/loading` endpoint to serve `startup.html` instead of `loading.html`
- Add `/startup-status` (JSON) and `/startup-status/stream` (SSE) endpoints
- On agent start: open browser to the dashboard, start the orchestrator in a background thread/task
- After all prerequisite phases pass: proceed with the existing Docker Compose startup logic

The existing endpoints (`/health`, `/pick-folder`, `/files`, `/file-content`) remain unchanged.

This component depends on:
- StartupOrchestrator
- Flask
- Existing agent logic

# Wireframe

For the visual design of the startup dashboard, refer to the wireframe at: `ai/wireframes/startup-screen-improvement.html`

# Testing Notes

- Test with Docker not installed (rename docker binary temporarily or use a PATH without it)
- Test with Docker installed but daemon not running (`sudo systemctl stop docker` on Linux, quit Docker Desktop on macOS)
- Test with old Docker that only has `docker-compose` (hyphen) — should fail at phase 2
- Test with leftover containers running — should clean up automatically without asking
- Test with 1 port conflict, multiple port conflicts, and no conflicts
- Test on macOS, Linux, and Windows — port checking commands differ
- Verify all user-facing text is in Dutch
- Verify log output is in English
- Test a full relaunch after a failure — all phases should run cleanly from scratch, prior state (leftover containers, partial downloads) handled gracefully