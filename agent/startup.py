"""
Startup prerequisite orchestrator for the Archive App agent.

Runs 5 sequential checks before handing off to Docker Compose:
  1. docker_installed  — Docker binary present and working
  2. docker_version    — Docker Compose v2 available
  3. docker_running    — Docker daemon reachable
  4. cleanup           — Stop any leftover containers from a previous session
  5. port_check        — Required ports are free
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
    link:   str | None = None   # optional URL shown as a clickable remediation link


@dataclass
class PhaseState:
    id:     str
    label:  str
    status: PhaseStatus       = PhaseStatus.PENDING
    detail: str | None        = None
    errors: list[dict] | None = None
    link:   str | None        = None


@dataclass
class StartupState:
    current_phase: str | None      = None
    phases:        list[PhaseState] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase interface
# ---------------------------------------------------------------------------

class StartupPhase:
    async def execute(self) -> PhaseResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Phase 1 — Docker installed
# ---------------------------------------------------------------------------

class DockerInstalledCheck(StartupPhase):
    async def execute(self) -> PhaseResult:
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
    async def execute(self) -> PhaseResult:
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
    async def execute(self) -> PhaseResult:
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

    async def execute(self) -> PhaseResult:
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
            # Cleanup always succeeds — log and move on
            logger.warning(f"Phase 4: cleanup encountered an error (continuing): {e}")
            return PhaseResult(status=PhaseStatus.SUCCESS, detail="Vorige sessie opgeruimd")


# ---------------------------------------------------------------------------
# Phase 5 — Port availability
# ---------------------------------------------------------------------------

class PortCheckPhase(StartupPhase):
    def __init__(self, ports: list[int]):
        self.ports = ports

    async def execute(self) -> PhaseResult:
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
        ])
        self._phases: list[StartupPhase] = [
            DockerInstalledCheck(),
            DockerVersionCheck(),
            DockerRunningCheck(),
            CleanupPhase(compose_file),
            PortCheckPhase(ports=[4210, 8010, 7777, 5442, 11434]),
        ]
        self._on_update = None

    def set_update_callback(self, callback) -> None:
        self._on_update = callback

    async def run(self) -> bool:
        """Run all phases in order. Returns True if all passed, False on first failure."""
        for i, phase in enumerate(self._phases):
            phase_state = self.state.phases[i]
            self.state.current_phase = phase_state.id
            phase_state.status = PhaseStatus.RUNNING
            phase_state.detail = None
            phase_state.errors = None
            phase_state.link   = None
            self._notify()

            result = await phase.execute()

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
                }
                for p in self.state.phases
            ],
        }

    def _notify(self) -> None:
        if self._on_update:
            self._on_update(self.get_state_dict())
