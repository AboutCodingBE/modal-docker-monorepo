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
import subprocess
import sys
import threading
import time
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
# Flask app — filesystem bridge
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, origins=["http://localhost:4200"])


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/pick-folder")
def pick_folder():
    """
    Open a native folder picker dialog and return the selected path.
    This runs on the main thread via tkinter.
    """
    folder = _open_folder_dialog()
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
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=Select Archive Folder"],
                capture_output=True,
                text=True,
            )
            folder = result.stdout.strip()
            return folder if folder else None

        elif system == "Windows":
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description = 'Select Archive Folder';"
                "$d.ShowNewFolderButton = $false;"
                "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
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
    compose_path = get_compose_path()
    logger.info(f"Starting Docker services from {compose_path}...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", compose_path, "up", "-d", "--wait"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Docker services started successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start Docker services:\n{e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        logger.error("Docker not found. Please install Docker Desktop.")
        sys.exit(1)


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


def open_browser():
    url = CONFIG["frontend_url"]
    logger.info(f"Opening browser at {url}")
    time.sleep(2)  # small delay to let nginx finish starting
    webbrowser.open(url)


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

    if not args.dev:
        # Start Docker services
        start_docker_services()

        # Ensure cleanup on exit
        atexit.register(stop_docker_services)

        # Open browser in background thread
        threading.Thread(target=open_browser, daemon=True).start()

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # Start the agent API
    port = CONFIG["agent_port"]
    logger.info(f"Agent API listening on http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
