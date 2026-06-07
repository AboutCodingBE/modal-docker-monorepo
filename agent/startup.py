"""
Startup prerequisite orchestrator for the Archive App agent.

Phases:
  1. docker_installed  — Docker binary present and working
  2. docker_version    — Docker Compose v2 available
  3. docker_running    — Docker daemon reachable
  4. cleanup           — Stop any leftover containers from a previous session
  5. port_check        — Required ports are free
  6. pull_images       — Pull all Docker images (per-image progress via sub-steps)
  7. start_services    — Start each service and wait for health (sub-steps with logs)
"""

import asyncio
import logging
import platform
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("agent")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"


@dataclass
class PhaseResult:
    status: PhaseStatus
    detail: str | None = None
    errors: list[dict] | None = None
    link:   str | None = None


@dataclass
class SubStep:
    name:   str
    status: PhaseStatus   = PhaseStatus.PENDING
    detail: str | None    = None
    logs:   str | None    = None


@dataclass
class PhaseState:
    id:        str
    label:     str
    status:    PhaseStatus          = PhaseStatus.PENDING
    detail:    str | None           = None
    errors:    list[dict] | None    = None
    link:      str | None           = None
    sub_steps: list[SubStep] | None = None


@dataclass
class StartupState:
    current_phase: str | None       = None
    phases:        list[PhaseState] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase interface
# ---------------------------------------------------------------------------

class StartupPhase:
    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Phase 1 — Docker installed
# ---------------------------------------------------------------------------

class DockerInstalledCheck(StartupPhase):
    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 1: checking Docker installation")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return self._fail()
            version = self._parse_version(stdout.decode())
            logger.info(f"Phase 1: Docker found — {version}")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail=version)
        except FileNotFoundError:
            return self._fail()

    def _fail(self) -> PhaseResult:
        os_name = platform.system()
        links = {
            "Darwin":  "https://docs.docker.com/desktop/install/mac-install/",
            "Windows": "https://docs.docker.com/desktop/install/windows-install/",
            "Linux":   "https://docs.docker.com/engine/install/",
        }
        link = links.get(os_name, links["Linux"])
        logger.error("Phase 1: Docker not found")
        return PhaseResult(
            status=PhaseStatus.FAILED,
            detail="Docker is niet geïnstalleerd. Installeer Docker via de link hieronder en start de applicatie opnieuw.",
            link=link,
        )

    def _parse_version(self, output: str) -> str:
        match = re.search(r"Docker version\s+([\d.]+)", output)
        return f"Docker {match.group(1)}" if match else output.strip()


# ---------------------------------------------------------------------------
# Phase 2 — Docker Compose v2
# ---------------------------------------------------------------------------

class DockerVersionCheck(StartupPhase):
    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 2: checking Docker Compose v2")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return self._fail()
            version_line = stdout.decode().strip()
            match = re.search(r"(v[\d.]+)", version_line)
            detail = f"Docker Compose {match.group(1)}" if match else version_line
            logger.info(f"Phase 2: {detail}")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail=detail)
        except FileNotFoundError:
            return self._fail()

    def _fail(self) -> PhaseResult:
        logger.error("Phase 2: Docker Compose v2 not available")
        return PhaseResult(
            status=PhaseStatus.FAILED,
            detail="Docker Compose v2 is niet beschikbaar. Update Docker naar de laatste versie en start de applicatie opnieuw.",
            link="https://docs.docker.com/compose/install/",
        )


# ---------------------------------------------------------------------------
# Phase 3 — Docker daemon running
# ---------------------------------------------------------------------------

class DockerRunningCheck(StartupPhase):
    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 3: checking Docker daemon")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return self._fail()
            logger.info("Phase 3: Docker daemon is running")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail="Docker daemon actief")
        except FileNotFoundError:
            return self._fail()

    def _fail(self) -> PhaseResult:
        os_name = platform.system()
        if os_name == "Darwin":
            msg = "Docker is niet actief. Open Docker Desktop vanuit de Applications map en start de applicatie opnieuw."
        elif os_name == "Windows":
            msg = "Docker is niet actief. Start Docker Desktop vanuit het Start menu en start de applicatie opnieuw."
        else:
            msg = "Docker is niet actief. Start de Docker daemon met het commando hieronder en start de applicatie opnieuw."
        logger.error("Phase 3: Docker daemon not reachable")
        return PhaseResult(status=PhaseStatus.FAILED, detail=msg)


# ---------------------------------------------------------------------------
# Phase 4 — Cleanup previous session
# ---------------------------------------------------------------------------

class CleanupPhase(StartupPhase):
    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 4: checking for leftover containers")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file, "ps", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            container_ids = [c for c in stdout.decode().strip().split("\n") if c.strip()]

            if not container_ids:
                logger.info("Phase 4: no leftover containers found")
                return PhaseResult(status=PhaseStatus.SUCCESS, detail="Geen actieve sessie gevonden")

            count = len(container_ids)
            logger.info(f"Phase 4: stopping {count} leftover container(s)")

            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file, "down", "--timeout", "10",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=20)
            except asyncio.TimeoutError:
                logger.warning("Phase 4: graceful shutdown timed out, force stopping")
                proc.kill()
                proc2 = await asyncio.create_subprocess_exec(
                    "docker", "compose", "-f", self.compose_file, "down", "--timeout", "0",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc2.communicate()

            logger.info(f"Phase 4: stopped {count} container(s)")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail=f"{count} containers gestopt")

        except Exception as e:
            logger.warning(f"Phase 4: cleanup encountered an error (continuing): {e}")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail="Vorige sessie opgeruimd")


# ---------------------------------------------------------------------------
# Phase 5 — Port availability
# ---------------------------------------------------------------------------

class PortCheckPhase(StartupPhase):
    def __init__(self, ports: list[int]):
        self.ports = ports

    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info(f"Phase 5: checking ports {self.ports}")
        conflicts = []
        for port in self.ports:
            info = await self._check_port(port)
            if info:
                conflicts.append(info)

        if conflicts:
            logger.error(f"Phase 5: {len(conflicts)} port conflict(s) found")
            return PhaseResult(
                status=PhaseStatus.FAILED,
                detail="Sommige poorten zijn in gebruik. Sluit de processen en start de applicatie opnieuw.",
                errors=conflicts,
            )

        logger.info("Phase 5: all ports are free")
        return PhaseResult(status=PhaseStatus.SUCCESS)

    async def _check_port(self, port: int) -> dict | None:
        os_name = platform.system()
        if os_name in ("Darwin", "Linux"):
            return await self._check_port_unix(port)
        elif os_name == "Windows":
            return await self._check_port_windows(port)
        return None

    async def _check_port_unix(self, port: int) -> dict | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "lsof", "-i", f":{port}", "-t",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0 or not stdout.strip():
                return None

            pid = stdout.decode().strip().split("\n")[0].strip()
            if not pid:
                return None

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
                "fix": f"kill {pid}",
            }
        except Exception:
            return None

    async def _check_port_windows(self, port: int) -> dict | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "netstat", "-ano",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            pid = None
            for line in stdout.decode().splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                    break

            if not pid:
                return None

            proc2 = await asyncio.create_subprocess_exec(
                "tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            lines = [ln for ln in stdout2.decode().strip().splitlines() if ln.strip()]
            process_name = "onbekend"
            if lines:
                parts = lines[0].split(",")
                if parts:
                    process_name = parts[0].strip('"')

            return {
                "port": port,
                "process": process_name,
                "pid": int(pid),
                "message": f"Poort {port} is in gebruik door proces '{process_name}' (PID {pid})",
                "fix": f"taskkill /PID {pid} /F",
            }
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Phase 6 — Pull Docker images
# ---------------------------------------------------------------------------

class PullImagesPhase(StartupPhase):
    # Images in pull order: infrastructure first, app images last
    IMAGES = [
        ("postgres:16-alpine",                             "Database (PostgreSQL)"),
        ("apache/tika:latest-full",                        "Tika (tekstextractie)"),
        ("ollama/ollama:0.23.0",                           "Ollama (AI engine)"),
        ("ghcr.io/aboutcodingbe/archive-app-backend:latest",  "Backend (API)"),
        ("ghcr.io/aboutcodingbe/archive-app-frontend:latest", "Frontend (webinterface)"),
    ]

    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 6: pulling Docker images")

        phase_state.sub_steps = [SubStep(name=display) for _, display in self.IMAGES]
        notify()

        completed = 0
        needs_download = 0

        for i, (image, display) in enumerate(self.IMAGES):
            sub = phase_state.sub_steps[i]
            sub.status = PhaseStatus.RUNNING
            sub.detail = "Controleren..."
            notify()

            logger.info(f"Phase 6: pulling {image}")

            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "pull", image,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                output_lines = []
                async for line in proc.stdout:
                    decoded = line.decode()
                    output_lines.append(decoded)
                    # Detect active download and update detail in real-time
                    if sub.detail == "Controleren..." and any(
                        k in decoded for k in ("Pulling from", "Pulling fs layer", "Downloading")
                    ):
                        sub.detail = "Downloaden..."
                        notify()

                stderr_data = await proc.stderr.read()
                await proc.wait()

                full_output = "".join(output_lines) + stderr_data.decode()

                if proc.returncode != 0:
                    error_msg = self._parse_error(full_output)
                    sub.status = PhaseStatus.FAILED
                    sub.detail = error_msg
                    notify()
                    logger.error(f"Phase 6: failed to pull {image}: {error_msg}")
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail=f"Fout bij downloaden van {display}. Start de applicatie opnieuw na het oplossen van het probleem.",
                    )

                if "up to date" in full_output.lower() or "image is up to date" in full_output.lower():
                    sub.status = PhaseStatus.SUCCESS
                    sub.detail = "Al beschikbaar"
                else:
                    sub.status = PhaseStatus.SUCCESS
                    sub.detail = "Gedownload"
                    needs_download += 1

                completed += 1
                phase_state.detail = f"{completed} van {len(self.IMAGES)} images gereed"
                notify()
                logger.info(f"Phase 6: {image} — {sub.detail}")

            except Exception as e:
                sub.status = PhaseStatus.FAILED
                sub.detail = str(e)
                notify()
                logger.error(f"Phase 6: exception pulling {image}: {e}")
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"Fout bij downloaden van {display}. Start de applicatie opnieuw na het oplossen van het probleem.",
                )

        suffix = " (eerste keer opstarten — dit is eenmalig)" if needs_download > 2 else ""
        logger.info(f"Phase 6: all images ready ({needs_download} downloaded)")
        return PhaseResult(
            status=PhaseStatus.SUCCESS,
            detail=f"{completed} van {len(self.IMAGES)} images gereed{suffix}",
        )

    def _parse_error(self, output: str) -> str:
        lower = output.lower()
        if "not found" in lower or "does not exist" in lower:
            return "Image niet gevonden. Neem contact op met de beheerder."
        if "unauthorized" in lower or "denied" in lower or "forbidden" in lower:
            return "Toegang geweigerd. Neem contact op met de beheerder."
        if "network" in lower or "timeout" in lower or "unreachable" in lower:
            return "Geen internetverbinding. Controleer uw netwerkverbinding en start de applicatie opnieuw."
        return output.strip()[-200:]


# ---------------------------------------------------------------------------
# Phase 7 — Start services
# ---------------------------------------------------------------------------

@dataclass
class ServiceDef:
    compose_name:  str
    display_name:  str
    health_method: str        # "docker_health" or "http"
    health_url:    str | None
    timeout:       int
    poll_interval: int
    depends_on:    list[str]


class StartServicesPhase(StartupPhase):
    SERVICES = [
        ServiceDef("db",       "Database (PostgreSQL)",  "docker_health", None,                            60,  3, []),
        ServiceDef("tika",     "Tika (tekstextractie)",  "http",          "http://localhost:7777/version",  120, 5, []),
        ServiceDef("ollama",   "Ollama (AI engine)",     "http",          "http://localhost:11434/api/tags", 60,  3, []),
        ServiceDef("backend",  "Backend (API)",          "docker_health", None,                            120, 5, ["db", "tika"]),
        ServiceDef("frontend", "Frontend (webinterface)", "http",         "http://localhost:4210",          60,  3, ["backend"]),
    ]

    def __init__(self, compose_file: str):
        self.compose_file = compose_file

    async def execute(self, phase_state: PhaseState = None, notify: callable = None) -> PhaseResult:
        logger.info("Phase 7: starting services")

        phase_state.sub_steps = [SubStep(name=svc.display_name) for svc in self.SERVICES]
        notify()

        for i, svc in enumerate(self.SERVICES):
            sub = phase_state.sub_steps[i]

            # Check that all dependencies succeeded
            for dep_name in svc.depends_on:
                dep_idx = next(j for j, s in enumerate(self.SERVICES) if s.compose_name == dep_name)
                if phase_state.sub_steps[dep_idx].status == PhaseStatus.FAILED:
                    sub.status = PhaseStatus.FAILED
                    sub.detail = f"Overgeslagen: {self.SERVICES[dep_idx].display_name} is niet beschikbaar"
                    notify()
                    logger.error(f"Phase 7: skipping {svc.compose_name} — dependency failed")
                    return PhaseResult(
                        status=PhaseStatus.FAILED,
                        detail=f"{svc.display_name} kon niet worden gestart vanwege een mislukte afhankelijkheid. Start de applicatie opnieuw na het oplossen van het probleem.",
                    )

            # Start the service
            logger.info(f"Phase 7: starting {svc.compose_name}")
            sub.status = PhaseStatus.RUNNING
            sub.detail = "Opstarten..."
            notify()

            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file, "up", "-d", svc.compose_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err = stderr.decode().strip()[-300:]
                sub.status = PhaseStatus.FAILED
                sub.detail = f"Kon niet worden gestart"
                sub.logs = err
                notify()
                logger.error(f"Phase 7: failed to start {svc.compose_name}: {err}")
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"{svc.display_name} kon niet worden gestart. Controleer de logs hieronder en start de applicatie opnieuw.",
                )

            # Wait for health
            sub.detail = "Wachten op gezondheidscontrole..."
            notify()

            healthy = await self._wait_for_health(svc)

            if healthy:
                sub.status = PhaseStatus.SUCCESS
                sub.detail = "Gezond"
                notify()
                logger.info(f"Phase 7: {svc.compose_name} is healthy")
            else:
                sub.status = PhaseStatus.FAILED
                sub.detail = f"Niet gezond na {svc.timeout} seconden"
                sub.logs = await self._fetch_logs(svc.compose_name)
                notify()
                logger.error(f"Phase 7: {svc.compose_name} did not become healthy within {svc.timeout}s")
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    detail=f"{svc.display_name} kon niet worden gestart. Controleer de logs hieronder en start de applicatie opnieuw.",
                )

        logger.info("Phase 7: all services are healthy")
        return PhaseResult(status=PhaseStatus.SUCCESS, detail="Alle services zijn actief")

    async def _wait_for_health(self, svc: ServiceDef) -> bool:
        elapsed = 0
        while elapsed < svc.timeout:
            ok = False
            if svc.health_method == "docker_health":
                ok = await self._check_docker_health(svc.compose_name)
            elif svc.health_method == "http":
                ok = await self._check_http_health(svc.health_url)
            if ok:
                return True
            await asyncio.sleep(svc.poll_interval)
            elapsed += svc.poll_interval
        return False

    async def _check_docker_health(self, service_name: str) -> bool:
        try:
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
        except Exception:
            return False

    async def _check_http_health(self, url: str) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)
                return resp.status_code == 200
        except Exception:
            return False

    async def _fetch_logs(self, service_name: str) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", self.compose_file,
                "logs", service_name, "--tail", "50",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return (stdout.decode() + stderr.decode()).strip()[-2000:]
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class StartupOrchestrator:
    def __init__(self, compose_file: str):
        self.compose_file = compose_file
        self.state = StartupState(phases=[
            PhaseState(id="docker_installed", label="Docker geïnstalleerd"),
            PhaseState(id="docker_version",   label="Docker Compose compatibel"),
            PhaseState(id="docker_running",   label="Docker actief"),
            PhaseState(id="cleanup",          label="Vorige sessie opruimen"),
            PhaseState(id="port_check",       label="Poorten beschikbaar"),
            PhaseState(id="pull_images",      label="Docker images downloaden"),
            PhaseState(id="start_services",   label="Services opstarten"),
        ])
        self._phases: list[StartupPhase] = [
            DockerInstalledCheck(),
            DockerVersionCheck(),
            DockerRunningCheck(),
            CleanupPhase(compose_file),
            PortCheckPhase(ports=[4210, 8010, 7777, 5442, 11434]),
            PullImagesPhase(compose_file),
            StartServicesPhase(compose_file),
        ]
        self._on_update = None

    def set_update_callback(self, callback) -> None:
        self._on_update = callback

    async def run(self) -> bool:
        """Run all phases in order. Returns True if all passed, False on first failure."""
        for i, phase in enumerate(self._phases):
            phase_state = self.state.phases[i]
            self.state.current_phase = phase_state.id
            phase_state.status    = PhaseStatus.RUNNING
            phase_state.detail    = None
            phase_state.errors    = None
            phase_state.link      = None
            phase_state.sub_steps = None
            self._notify()

            result = await phase.execute(phase_state, self._notify)

            phase_state.status = result.status
            phase_state.detail = result.detail
            phase_state.errors = result.errors
            phase_state.link   = result.link
            self._notify()

            if result.status == PhaseStatus.FAILED:
                return False

        return True

    def get_state_dict(self) -> dict:
        return {
            "current_phase": self.state.current_phase,
            "phases": [
                {
                    "id":     p.id,
                    "label":  p.label,
                    "status": p.status.value,
                    "detail": p.detail,
                    "errors": p.errors,
                    "link":   p.link,
                    "sub_steps": [
                        {
                            "name":   s.name,
                            "status": s.status.value,
                            "detail": s.detail,
                            "logs":   s.logs,
                        }
                        for s in p.sub_steps
                    ] if p.sub_steps else None,
                }
                for p in self.state.phases
            ],
        }

    def _notify(self) -> None:
        if self._on_update:
            self._on_update(self.get_state_dict())
