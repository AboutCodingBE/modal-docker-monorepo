"""
Archive App Local Agent
=======================
This is the only native component. It serves two roles:
1. Application launcher — starts Docker services, opens the browser
2. Filesystem bridge — exposes file picker and file streaming endpoints

The agent runs on the host machine (not in Docker).
"""

import asyncio
import json
import logging
import mimetypes
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file, Response, stream_with_context
from flask_cors import CORS

from startup import StartupOrchestrator

# ---------------------------------------------------------------------------
# Configuration (can be overridden via config.json alongside this script)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "agent_port": 9090,
    "frontend_url": "http://localhost:4210",
    "compose_file": "../docker-compose.yml",
    "log_file": "~/.archive-app/agent.log",
}


def _base_dir() -> Path:
    """Returns the directory containing the executable (PyInstaller bundle)
    or the script file (normal Python run)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def _resources_dir() -> Path:
    """Returns the directory where PyInstaller extracts bundled data,
    or the script directory for normal Python runs."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config_path = _base_dir() / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config.update(json.load(f))
    return config


CONFIG = load_config()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_path = Path(CONFIG["log_file"]).expanduser()
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("agent")

# ---------------------------------------------------------------------------
# Startup state (written by orchestrator, read by /startup-status endpoints)
# ---------------------------------------------------------------------------
_startup_events: list[dict] = []        # accumulated state snapshots (append-only)
_startup_done   = threading.Event()     # set when orchestrator finishes (pass or fail)
_orchestrator: StartupOrchestrator | None = None


def _on_startup_state_update(state: dict) -> None:
    _startup_events.append(state)

# ---------------------------------------------------------------------------
# Flask app — filesystem bridge
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, origins=[CONFIG["frontend_url"], "http://localhost:9090"])


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/startup-status")
def startup_status():
    if _orchestrator is not None:
        return jsonify(_orchestrator.get_state_dict())
    # Orchestrator not yet initialised — return empty pending state
    return jsonify({"current_phase": None, "phases": []})


@app.get("/startup-status/stream")
def startup_status_stream():
    """SSE stream: pushes a full state snapshot on every phase change."""
    def generate():
        idx = 0
        while True:
            if idx < len(_startup_events):
                data = json.dumps(_startup_events[idx])
                yield f"data: {data}\n\n"
                idx += 1
            elif _startup_done.is_set():
                break
            else:
                time.sleep(0.1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health/backend")
def health_backend():
    """Proxy health check to the frontend/backend (avoids CORS on the loading page)."""
    try:
        with urllib.request.urlopen(CONFIG["frontend_url"] + "/api/health", timeout=2) as resp:
            if resp.status == 200:
                return jsonify({"status": "ok"})
    except Exception:
        pass
    return jsonify({"status": "unavailable"}), 503


@app.get("/loading")
def loading_page():
    html = (_resources_dir() / "templates" / "startup.html").read_text(encoding="utf-8")
    return Response(html, mimetype="text/html")


@app.post("/pick-folder")
def pick_folder():
    """
    Open a native folder picker dialog and return the selected path.
    """
    try:
        folder = _open_folder_dialog()
    except FolderPickerError as e:
        return jsonify({"error": str(e)}), 400
    if folder is None:
        return jsonify({"error": "No folder selected"}), 400
    return jsonify({"path": folder})


@app.get("/files")
def list_files():
    """
    List all files recursively under the given path.
    Returns flat list with relative paths, sizes, and parent folders.
    Query param: path (required)
    """
    root = request.args.get("path")
    if not root or not os.path.isdir(root):
        return jsonify({"error": "Invalid or missing path"}), 400

    entries = []
    root_path = Path(root)

    # Collect and sort all entries so parent directories always come before children
    all_paths = sorted(root_path.rglob("*"), key=lambda p: len(p.parts))

    for file_path in all_paths:
        relative_path = str(file_path.relative_to(root_path))
        parent_folder = str(file_path.parent.relative_to(root_path))
        if file_path.is_dir():
            entries.append({
                "name": file_path.name,
                "relative_path": relative_path,
                "absolute_path": str(file_path),
                "parent_folder": parent_folder,
                "is_directory": True,
                "size_bytes": None,
                "modified": None,
            })
        elif file_path.is_file():
            stat = file_path.stat()
            entries.append({
                "name": file_path.name,
                "relative_path": relative_path,
                "absolute_path": str(file_path),
                "parent_folder": parent_folder,
                "is_directory": False,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
            })

    files = [e for e in entries if not e["is_directory"]]
    return jsonify({"root": root, "total_files": len(files), "files": entries})


@app.get("/file-content")
def file_content():
    """
    Stream the contents of a specific file.
    Query param: path (required) — absolute path to the file.
    """
    file_path = request.args.get("path")
    if not file_path or not os.path.isfile(file_path):
        return jsonify({"error": "Invalid or missing file path"}), 400

    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return send_file(file_path, mimetype=mime_type)


# ---------------------------------------------------------------------------
# Folder picker (platform-native via subprocess)
# ---------------------------------------------------------------------------
class FolderPickerError(Exception):
    """Raised when a required platform tool for folder picking is unavailable."""
    pass


def _open_folder_dialog() -> str | None:
    """
    Open a native folder picker dialog synchronously using platform tools:
    - macOS:   osascript (AppleScript choose folder)
    - Linux:   zenity --file-selection --directory
    - Windows: PowerShell FolderBrowserDialog
    """
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'POSIX path of (choose folder with prompt "Select Archive Folder")',
                ],
                capture_output=True,
                text=True,
            )
            folder = result.stdout.strip().rstrip("/")
            return folder if folder else None

        elif system == "Linux":
            try:
                result = subprocess.run(
                    [
                        "zenity", "--file-selection", "--directory",
                        "--title=Select Archive Folder",
                        "--modal",
                    ],
                    capture_output=True,
                    text=True,
                    env=os.environ.copy(),
                )
            except FileNotFoundError:
                raise FolderPickerError(
                    "zenity is not installed. Please install it with: sudo apt install zenity"
                )
            folder = result.stdout.strip()
            return folder if folder else None

        elif system == "Windows":
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$topmost = New-Object System.Windows.Forms.Form;"
                "$topmost.TopMost = $true;"
                "$topmost.StartPosition = 'CenterScreen';"
                "$topmost.WindowState = 'Minimized';"
                "$topmost.Show();"
                "$topmost.WindowState = 'Normal';"
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description = 'Select Archive Folder';"
                "$d.ShowNewFolderButton = $false;"
                "if ($d.ShowDialog($topmost) -eq 'OK') { $d.SelectedPath };"
                "$topmost.Close()"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
            )
            folder = result.stdout.strip()
            return folder if folder else None

        else:
            logger.error(f"Unsupported platform for folder picker: {system}")
            return None

    except FolderPickerError:
        raise
    except FileNotFoundError as e:
        logger.error(f"Folder picker tool not found: {e}")
        return None
    except Exception as e:
        logger.error(f"Folder dialog error: {e}")
        return None


# ---------------------------------------------------------------------------
# Docker lifecycle management
# ---------------------------------------------------------------------------
def get_compose_path() -> str:
    return str((_base_dir() / CONFIG["compose_file"]).resolve())


def start_docker_services():
    global _startup_status
    compose_path = get_compose_path()
    logger.info(f"Starting Docker services from {compose_path}...")
    logger.info("Pulling latest images, this may take a moment...")
    try:
        process = subprocess.Popen(
            ["docker", "compose", "-f", compose_path, "up", "-d", "--pull", "always", "--wait"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for line in process.stdout:
            line = line.strip()
            if line and any(keyword in line.lower() for keyword in [
                "pulling", "pulled", "created", "started",
                "healthy", "error", "failed", "warning",
                "waiting", "running", "downloading", "downloaded",
            ]):
                logger.info(f"Docker: {line}")

        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, "docker compose")

        logger.info("Docker services started successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start Docker services (exit code {e.returncode})")
        _startup_status = {
            "status": "failed",
            "error": "Failed to start services. Check the logs at ~/.archive-app/agent.log",
        }
    except FileNotFoundError:
        logger.error("Docker not found. Please install Docker Desktop.")
        _startup_status = {
            "status": "failed",
            "error": "Docker not found. Please install Docker Desktop and try again.",
        }


def stop_docker_services():
    compose_path = get_compose_path()
    logger.info("Stopping Docker services...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", compose_path, "down"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Docker services stopped.")
    except Exception as e:
        logger.error(f"Error stopping Docker services: {e}")


def _wait_for_flask(port: int, timeout: float = 10.0) -> None:
    """Block until Flask is accepting TCP connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    logger.warning("Flask did not become ready within timeout — continuing anyway.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    import argparse
    import atexit
    import signal

    parser = argparse.ArgumentParser(description="Archive App Local Agent")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Dev mode: skip Docker lifecycle management and browser opening. "
             "Only starts the filesystem bridge API on localhost:9090.",
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Archive App Agent starting%s", " [DEV MODE]" if args.dev else "")
    logger.info("=" * 50)

    port = CONFIG["agent_port"]

    if args.dev:
        logger.info(f"Agent API listening on http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=False)
        return

    # ── Production startup sequence ──────────────────────────────────────────
    global _orchestrator

    # 1. Start Flask in a background thread so /loading is immediately available
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
        daemon=True,
    )
    flask_thread.start()

    # 2. Wait until Flask is accepting connections
    _wait_for_flask(port)

    # 3. Open the browser to the startup dashboard
    loading_url = f"http://localhost:{port}/loading"
    logger.info(f"Opening browser at {loading_url}")
    webbrowser.open(loading_url)

    # 4. Run prerequisite checks (blocks until all pass or one fails)
    compose_path = get_compose_path()
    _orchestrator = StartupOrchestrator(compose_path, CONFIG)
    _orchestrator.set_update_callback(_on_startup_state_update)

    logger.info("Running startup prerequisite checks...")
    prerequisites_ok = asyncio.run(_orchestrator.run())
    _startup_done.set()

    if not prerequisites_ok:
        # Dashboard shows the actionable error; keep the agent alive so the
        # browser can still read /startup-status and /startup-status/stream.
        logger.error("Prerequisite checks failed — fix the issue and relaunch the agent.")
        signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while True:
            time.sleep(1)
        return

    logger.info("All prerequisite checks passed — services are running.")

    # 5. Register Docker cleanup on exit
    atexit.register(stop_docker_services)

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # 6. Keep the main thread alive so the daemon Flask thread keeps running
    logger.info(f"Agent API listening on http://localhost:{port}")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
