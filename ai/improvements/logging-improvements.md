Set up structured logging for the backend with separate log
files per feature and a consistent format.

## Log directory
- In Docker: write to /app/logs/ (will be volume-mounted to
  the host)
- In local dev: write to ~/.archive-app/logs/
- Detect which to use based on whether running in Docker
  (check for /.dockerenv file or an environment variable)

## Add volume mount to both docker-compose files
backend:
volumes:
- ~/.archive-app/logs:/app/logs

## Log files
- app.log — catch-all, receives everything from all loggers
- tika.log — tika extraction only
- summary.log — AI summarization only
- ingestion.log — file inventory and ingestion only

## Log format
Every line must follow this format:
2026-04-25 14:30:12 [ERROR] [archive:50cebbe8] [file:brief-1920.pdf] Message here

- Timestamp: YYYY-MM-DD HH:MM:SS
- Level: ERROR, WARN, INFO
- Archive context: first 8 characters of the archive UUID
- File context: the file name (not the UUID)
- Message: what happened

When archive or file context is not applicable (e.g.,
startup logs), omit those brackets.

## Logger setup
Create a logging configuration module (e.g.,
app/shared/logging_config.py) that sets up:

- Named loggers: app.tika, app.summary, app.ingestion
- Each named logger writes to its own file AND to app.log
- All loggers also output to stdout (for docker compose logs)
- Use Python's logging module with FileHandler per logger
- Log rotation: RotatingFileHandler, max 10MB per file,
  keep 3 backups

## What to log per feature

### tika.log (logger: app.tika)
- ERROR: extraction failed — include archive id, file name,
  and the exception/reason (timeout, connection error,
  unsupported format, etc.)
- WARN: empty content returned — file processed but Tika
  returned no text
- INFO: optional — successful extractions (optional, can be
  noisy — make configurable)

### summary.log (logger: app.summary)
- ERROR: Ollama unreachable, model not found, generation
  failed — include archive id, file name, exception
- WARN: file skipped — include reason (too few words, no
  tika content available)
- INFO: optional — successful summaries

### ingestion.log (logger: app.ingestion)
- ERROR: agent unreachable, file streaming failed, database
  write failed — include archive id, file name, exception
- WARN: file skipped — include reason (permission error,
  symlink, unreadable)
- INFO: inventory started/completed with total file count

### app.log
- Receives all of the above
- Plus: startup/shutdown, migration results, health check
  failures, task lifecycle (started, completed, failed)

## Integration
Update the existing code in these features to use the
appropriate named logger instead of print() statements:
- create_summaries_for_archive — replace print() with
  summary_logger
- tika processing — replace print() with tika_logger
- ingestion/folder analysis — replace print() with
  ingestion_logger

Use a helper function to format the archive/file context
so it's consistent everywhere:

def log_context(archive_id: uuid.UUID, file_name: str = None) -> str:
ctx = f"[archive:{archive_id}]"
if file_name:
ctx += f" [file:{file_name}]"
return ctx

## Important
- Replace ALL existing print() statements in the backend
  with proper logger calls
- All datetime fields must be datetime objects, not strings
- Make sure the log directory is created if it doesn't exist