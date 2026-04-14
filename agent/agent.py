"""
Archive App Local Agent
=======================
This is the only native component. It serves two roles:
1. Application launcher — starts Docker services, opens the browser
2. Filesystem bridge — exposes file picker and file streaming endpoints

The agent runs on the host machine (not in Docker).
"""

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

from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Configuration (can be overridden via config.json alongside this script)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "agent_port": 9090,
    "frontend_url": "http://localhost:4200",
    "compose_file": "../docker-compose.yml",
    "log_file": "~/.archive-app/agent.log",
}


def _base_dir() -> Path:
    """Returns the directory containing the executable (PyInstaller bundle)
    or the script file (normal Python run)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
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
# Startup status (written by main thread, read by /startup-status endpoint)
# ---------------------------------------------------------------------------
_startup_status: dict = {"status": "starting", "error": None}

# ---------------------------------------------------------------------------
# Flask app — filesystem bridge
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, origins=["http://localhost:4200", "http://localhost:9090"])


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/startup-status")
def startup_status():
    return jsonify(_startup_status)


@app.get("/health/backend")
def health_backend():
    """Proxy health check to the frontend/backend (avoids CORS on the loading page)."""
    try:
        with urllib.request.urlopen("http://localhost:4200/api/health", timeout=2) as resp:
            if resp.status == 200:
                return jsonify({"status": "ok"})
    except Exception:
        pass
    return jsonify({"status": "unavailable"}), 503


@app.get("/loading")
def loading_page():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Archive App — Starting</title>
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: #1a1d27;
      border: 1px solid #2d3148;
      border-radius: 16px;
      padding: 48px 56px;
      text-align: center;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 25px 50px rgba(0, 0, 0, 0.4);
    }
    .logo {
      font-size: 26px;
      font-weight: 700;
      color: #a78bfa;
      letter-spacing: -0.5px;
      margin-bottom: 6px;
    }
    .tagline {
      font-size: 13px;
      color: #4b5563;
      margin-bottom: 40px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .spinner-wrap { margin: 0 auto 32px; width: 52px; height: 52px; }
    .spinner {
      width: 52px;
      height: 52px;
      border: 3px solid #2d3148;
      border-top-color: #a78bfa;
      border-radius: 50%;
      animation: spin 0.85s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .status {
      font-size: 15px;
      color: #94a3b8;
      min-height: 24px;
      transition: opacity 0.3s ease;
    }
    /* error state */
    .error-icon {
      font-size: 44px;
      margin-bottom: 16px;
      display: none;
    }
    .error-box {
      font-size: 13px;
      color: #fca5a5;
      background: #1f1010;
      border: 1px solid #7f1d1d;
      border-radius: 8px;
      padding: 14px 16px;
      text-align: left;
      line-height: 1.7;
      display: none;
      margin-top: 24px;
    }
    .is-error .spinner-wrap { display: none; }
    .is-error .error-icon { display: block; }
    .is-error .error-box { display: block; }
    .is-error .status { display: none; }
  </style>
</head>
<body>
  <div class="card" id="card">
    <div class="logo">MODAL</div>
    <div class="tagline">Archief browser</div>
    <div class="spinner-wrap"><div class="spinner"></div></div>
    <div class="error-icon">&#9888;&#65039;</div>
    <div class="status" id="status">MODAL app bezig met opstarten...</div>
    <div class="error-box" id="error-box"></div>
  </div>
  <script>
    const FRONTEND = 'http://localhost:4200';
    const AGENT    = '';
    const messages = [
      'Starting database...',
      'Starting analysis services...',
      'Starting backend...',
      'Almost ready...',
    ];
    let msgIdx = 0;
    const statusEl  = document.getElementById('status');
    const card      = document.getElementById('card');
    const errorBox  = document.getElementById('error-box');
    let stopped = false;

    function stop() { stopped = true; }

    function showError(msg) {
      stop();
      card.classList.add('is-error');
      errorBox.textContent = msg;
    }

    // Cycle status messages
    const msgTimer = setInterval(() => {
      if (stopped) { clearInterval(msgTimer); return; }
      msgIdx = (msgIdx + 1) % messages.length;
      statusEl.style.opacity = '0';
      setTimeout(() => {
        statusEl.textContent = messages[msgIdx];
        statusEl.style.opacity = '1';
      }, 300);
    }, 4000);

    // Poll agent startup-status for failures
    async function checkStartupStatus() {
      if (stopped) return;
      try {
        const res = await fetch(AGENT + '/startup-status');
        const data = await res.json();
        if (data.status === 'failed') {
          showError(data.error || 'Failed to start services. Check the logs at ~/.archive-app/agent.log');
          return;
        }
      } catch (_) {}
      setTimeout(checkStartupStatus, 3000);
    }

    // Poll backend health via agent proxy (same origin — no CORS)
    async function checkHealth() {
      if (stopped) return;
      try {
        const res = await fetch(AGENT + '/health/backend', {
          signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
          stop();
          statusEl.textContent = 'Ready! Redirecting...';
          setTimeout(() => { window.location.href = FRONTEND; }, 500);
          return;
        }
      } catch (_) {}
      setTimeout(checkHealth, 3000);
    }

    checkStartupStatus();
    checkHealth();
  </script>
</body>
</html>"""
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
    try:
        subprocess.run(
            ["docker", "compose", "-f", compose_path, "up", "-d","--pull", "always", "--wait"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Docker services started successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start Docker services:\n{e.stderr}")
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
    # 1. Start Flask in a background thread so /loading is immediately available
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
        daemon=True,
    )
    flask_thread.start()

    # 2. Wait until Flask is accepting connections
    _wait_for_flask(port)

    # 3. Open the browser to the loading page straight away
    loading_url = f"http://localhost:{port}/loading"
    logger.info(f"Opening browser at {loading_url}")
    webbrowser.open(loading_url)

    # 4. Register Docker cleanup on exit
    atexit.register(stop_docker_services)

    # 5. Start Docker services (blocks until done or failed)
    start_docker_services()

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # 6. Keep the main thread alive so the daemon Flask thread keeps running
    logger.info(f"Agent API listening on http://localhost:{port}")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
