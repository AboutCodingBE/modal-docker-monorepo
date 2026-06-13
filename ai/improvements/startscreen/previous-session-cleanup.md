# Use Case

When a user starts the agent while a previous instance is still running (e.g. they closed the browser without stopping the app, then double-clicked the agent again), the new agent should detect the old one and kill it before starting. This prevents duplicate agent processes consuming memory and port conflicts.

The input of this use case:
User starts the agent binary. No additional input needed.

Input mechanism of this use case:
Automatic — the agent checks for a previous instance at the very beginning of startup, before starting Flask.

The output of this feature:
- If a previous agent is running: its process is killed, then the new agent starts normally. Phase 4 (cleanup) handles stopping any leftover Docker containers.
- If no previous agent is running: startup proceeds as before, no change.

# Business Rules

- The previous agent check must happen BEFORE the new agent starts Flask. Otherwise both agents fight for the same port.
- Detection: check if a process is listening on the agent port (default 9090). If yes, it's a previous agent.
- Kill the process directly — no HTTP calls, no graceful shutdown. Just find the PID and kill it.
- After killing, wait briefly (up to 2 seconds) for the port to become free before continuing.
- If the port doesn't free up within 2 seconds, log a warning and attempt to continue anyway.
- Docker containers from the previous session are NOT stopped here — Phase 4 (cleanup previous session) in the startup orchestrator already handles that.
- Platform-specific process detection:
    - macOS/Linux: use `lsof -i :<port> -t` to get the PID
    - Windows: use `netstat -ano | findstr :<port>` to get the PID
- Platform-specific process killing:
    - macOS/Linux: `os.kill(pid, signal.SIGTERM)`
    - Windows: `subprocess.run(["taskkill", "/PID", str(pid), "/F"])`
- Log what's happening: "Previous agent detected (PID 12345) — stopping...", "Previous agent stopped.", etc.

# Component Overview

## Previous agent detection and cleanup

**File:** `agent/agent.py`

Add a function that checks for and kills a previous agent:

```python
def _kill_previous_agent(port: int) -> None:
    """If a previous agent is running on our port, kill it and wait for the port to free up."""
    pid = _find_pid_on_port(port)
    if pid is None:
        return  # No previous agent running

    logger.info("Previous agent detected (PID %d) — stopping...", pid)

    # Kill the process
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        logger.warning("Could not kill previous agent (PID %d): %s", pid, e)
        return

    # Wait for the port to free up
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                time.sleep(0.5)  # Port still in use, keep waiting
        except OSError:
            logger.info("Previous agent has stopped.")
            return

    logger.warning(
        "Previous agent did not release port %d within 5 seconds. "
        "Attempting to start anyway.",
        port,
    )


def _find_pid_on_port(port: int) -> int | None:
    """Find the PID of the process listening on the given port. Returns None if port is free."""
    system = platform.system()

    try:
        if system in ("Darwin", "Linux"):
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            # lsof may return multiple PIDs (one per connection), take the first
            pid_str = result.stdout.strip().split("\n")[0]
            return int(pid_str)

        elif system == "Windows":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                # Look for LISTENING on our port
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid_str = parts[-1]
                    return int(pid_str)
            return None

    except Exception as e:
        logger.warning("Could not check for previous agent on port %d: %s", port, e)
        return None

    return None
```
Note: This is a code example. Use constants instead of 'magic numbers'
Note: `signal` is already available in Python's standard library. Make sure `import signal` is at the top of agent.py (it may already be there since signal handlers are used in `main()`).

## Call the check at startup

**File:** `agent/agent.py`

In the `main()` function, call `_kill_previous_agent` at the very beginning, before starting Flask. This applies to both production and dev mode:

```python
def main():
    # ... argparse setup ...

    logger.info("=" * 50)
    logger.info("Archive App Agent starting%s", " [DEV MODE]" if args.dev else "")
    logger.info("=" * 50)

    port = CONFIG["agent_port"]

    # Kill any previous agent instance on our port
    _kill_previous_agent(port)

    if args.dev:
        # ... dev mode startup ...
```

The check must be BEFORE `app.run()` or `flask_thread.start()` — if the port is still occupied, Flask will fail to bind.

## No changes needed

- **StartupOrchestrator** — no changes. Phase 4 (cleanup) already handles stopping leftover Docker containers.
- **startup.html** — no changes. The kill is invisible to the user — by the time the browser opens, the old agent is already gone.
- **Docker Compose** — no changes. Phase 4 handles container cleanup.
- **Frontend** — no changes.
- **No new endpoints** — the `/shutdown` endpoint will be added later when implementing the "Applicatie stoppen" button in the frontend.

# Testing Notes

- Start the agent, close the browser (don't stop the agent), start the agent again. The second instance should kill the first and start normally.
- Verify only one agent process is running after the restart (check with `ps aux | grep archive-agent` on macOS/Linux, or Task Manager on Windows).
- Verify Docker containers from the previous session are cleaned up by Phase 4 (not by the kill — the kill only stops the agent process).
- Start the agent when no previous instance is running — should proceed immediately without delays.
- Test on macOS, Linux, and Windows — process detection and killing differs per platform.
- Verify the agent log shows "Previous agent detected (PID XXXX) — stopping..." and "Previous agent has stopped." messages.
- Test edge case: another process (not the agent) is on port 9090 — it will be killed. This is acceptable since port 9090 is reserved for the agent. The port check in Phase 5 already excludes 9090.