import logging
import os
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_dir() -> Path:
    if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
        return Path("/app/logs")
    return Path.home() / ".archive-app" / "logs"


def log_context(archive_id: uuid.UUID = None, file_name: str = None) -> str:
    """Returns a formatted context prefix for log messages.

    Example outputs:
      "[archive:50cebbe8] [file:brief-1920.pdf] "
      "[archive:50cebbe8] "
      ""
    """
    ctx = ""
    if archive_id is not None:
        ctx += f"[archive:{archive_id}] "
    if file_name:
        ctx += f"[file:{file_name}] "
    return ctx


def _formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _rotating_file_handler(path: Path) -> RotatingFileHandler:
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=3)
    handler.setFormatter(_formatter())
    return handler


def setup_logging() -> None:
    """Configure structured logging for the backend.

    Named loggers (app.tika, app.summary, app.ingestion) each write to their
    own log file. All messages propagate to the root 'app' logger which writes
    to app.log and stdout.
    """
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = _formatter()

    # Root app logger — catch-all (app.log + stdout)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    app_logger.addHandler(_rotating_file_handler(log_dir / "app.log"))
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(formatter)
    app_logger.addHandler(stdout_handler)

    # Named feature loggers — write to their own file, propagate to 'app'
    for name, filename in [
        ("app.tika", "tika.log"),
        ("app.summary", "summary.log"),
        ("app.ingestion", "ingestion.log"),
    ]:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_rotating_file_handler(log_dir / filename))
        # propagate=True (default): messages also flow to app logger -> app.log + stdout
