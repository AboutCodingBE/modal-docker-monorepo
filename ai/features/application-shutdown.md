# Use Case

Allow users to shut down the entire application cleanly from the frontend. When the user clicks "Afsluiten", any running analyses are cancelled, Docker services are stopped, and the agent process exits. The next time the user opens the app, all analyses show the correct status (CANCELLED, not stuck on STARTED).

The input of this use case:
User clicks the "Afsluiten" button in the frontend.

Input mechanism of this use case:
1. Frontend calls `POST http://localhost:9090/shutdown` on the agent
2. Agent calls `POST http://localhost:4210/api/cancel-all-analyses` on the backend (through the frontend proxy, or directly on `http://localhost:8010/api/cancel-all-analyses`)
3. Agent runs `docker compose down`
4. Agent exits

The output of this feature:
- All running analyses are marked as CANCELLED in the database
- All running tasks are marked as CANCELLED in the database
- All Docker services are stopped
- The agent process exits
- The browser shows a "De applicatie is afgesloten" confirmation page (served by the agent before it exits, or a static page)

# Business Rules

## Shutdown sequence
1. Agent receives `/shutdown` request
2. Agent calls the backend's cancel-all-analyses endpoint
3. If the backend call fails (backend already down, timeout, etc.), continue anyway — don't block shutdown
4. Agent runs `docker compose -f <compose_file> down --timeout 10`
5. Agent returns a response to the frontend (so the UI can show confirmation)
6. Agent exits after a short delay (1-2 seconds to ensure the response is sent)

## Cancel all analyses
- Set `status = 'CANCELLED'` on all `ArchiveAnalysis` records where `status = 'STARTED'`
- Set `status = 'CANCELLED'` on all `AnalysisTask` records where `status IN ('PENDING', 'RUNNING')`
- This is a blunt database update — it does NOT gracefully stop the analysis loop. `docker compose down` kills the processes.
- The CANCELLED enum value must already exist in the database (from a previous or new migration). If it doesn't exist yet, this feature needs to add it.

## Frontend button
- The "Afsluiten" button should be accessible from the main application screen
- Clicking the button should show a confirmation dialog: "Weet u zeker dat u de applicatie wilt stoppen?" with "Stoppen" and "Annuleren" options
- After confirming, the frontend calls the agent shutdown endpoint
- After the call succeeds, show a message: "De applicatie is afgesloten. U kunt dit venster sluiten."
- If an analysis is running, the confirmation dialog should mention this: "Er is momenteel een analyse actief. Deze wordt gestopt als u verdergaat."

## Edge cases
- If no analyses are running: cancel-all endpoint still succeeds (updates 0 rows, returns 200)
- If the backend is already down: agent logs a warning and continues with docker compose down
- If docker compose down hangs: use --timeout 10 to force stop after 10 seconds
- The agent should NOT call cancel-all on the startup shutdown (when killing a previous agent). The startup flow uses `_kill_previous_agent` which just kills the process. Phase 4 cleans up containers. Database state may be inconsistent after a startup kill, but that's acceptable — a future enhancement could add a "fix stuck analyses" check on startup.

# Component Overview

## Backend: cancel_all_analyses feature

**New folder:** `backend/app/cancel_all_analyses/`

Following the existing feature folder pattern.

### `backend/app/cancel_all_analyses/__init__.py`
Empty file.

### `backend/app/cancel_all_analyses/router.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.cancel_all_analyses.cancel_all_analyses import CancelAllAnalyses

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/cancel-all-analyses")
async def cancel_all_analyses(db: AsyncSession = Depends(get_db)):
    result = await CancelAllAnalyses(db).execute()
    return result
```

### `backend/app/cancel_all_analyses/cancel_all_analyses.py`

```python
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.cancel_all_analyses.repository import CancelAllAnalysesRepository

_logger = logging.getLogger("app.cancel_all_analyses")


class CancelAllAnalyses:
    def __init__(self, session: AsyncSession):
        self._repo = CancelAllAnalysesRepository(session)
        self._session = session

    async def execute(self) -> dict:
        cancelled_analyses = await self._repo.cancel_running_analyses()
        cancelled_tasks = await self._repo.cancel_running_tasks()
        await self._session.commit()

        _logger.info(
            "Cancel all: %d analyses and %d tasks cancelled",
            cancelled_analyses,
            cancelled_tasks,
        )

        return {
            "cancelled_analyses": cancelled_analyses,
            "cancelled_tasks": cancelled_tasks,
        }
```

### `backend/app/cancel_all_analyses/repository.py`

```python
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ArchiveAnalysis, ArchiveAnalysisStatus, AnalysisTask


class CancelAllAnalysesRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def cancel_running_analyses(self) -> int:
        """Cancel all analyses with status STARTED. Returns number of rows updated."""
        result = await self._session.execute(
            update(ArchiveAnalysis)
            .where(ArchiveAnalysis.status == ArchiveAnalysisStatus.STARTED)
            .values(status=ArchiveAnalysisStatus.CANCELLED)
        )
        return result.rowcount

    async def cancel_running_tasks(self) -> int:
        """Cancel all tasks with status PENDING or RUNNING. Returns number of rows updated."""
        result = await self._session.execute(
            update(AnalysisTask)
            .where(AnalysisTask.status.in_(["PENDING", "RUNNING"]))
            .values(status="CANCELLED")
        )
        return result.rowcount
```

Note: The exact status field type for `AnalysisTask` may be a string or an enum. Check the model definition and adjust the query accordingly. If `AnalysisTask` uses a string field for status, use string values. If it uses an enum, use the enum values.

### Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.cancel_all_analyses.router import router as cancel_all_analyses_router

app.include_router(cancel_all_analyses_router)
```

## CANCELLED enum value

Check if `CANCELLED` already exists in `ArchiveAnalysisStatus` and in the database enum. If not, it needs to be added:

**File:** `backend/app/shared/models.py` — add `CANCELLED = "CANCELLED"` to `ArchiveAnalysisStatus`

**New migration** — add `CANCELLED` to the PostgreSQL enum:
```sql
ALTER TYPE archive_analysis_status ADD VALUE 'CANCELLED';
```

Same for `AnalysisTask` if it uses a PostgreSQL enum for status.

If these were already added as part of the cancel-analysis feature context we wrote earlier, no changes needed.

## Agent: /shutdown endpoint

**File:** `agent/agent.py`

Add the shutdown endpoint:

```python
@app.post("/shutdown")
def shutdown():
    """Shut down the application: cancel analyses, stop Docker, exit."""
    logger.info("Shutdown requested by user.")

    def _shutdown_sequence():
        # 1. Cancel running analyses
        try:
            req = urllib.request.Request(
                "http://localhost:8010/api/cancel-all-analyses",
                method="POST",
                data=b"",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                logger.info(
                    "Cancelled %d analyses and %d tasks.",
                    result.get("cancelled_analyses", 0),
                    result.get("cancelled_tasks", 0),
                )
        except Exception as e:
            logger.warning("Could not cancel analyses (backend may already be down): %s", e)

        # 2. Stop Docker services
        time.sleep(0.5)  # Brief pause to ensure response is sent
        stop_docker_services()

        # 3. Exit
        logger.info("Shutdown complete. Exiting.")
        os._exit(0)

    threading.Thread(target=_shutdown_sequence, daemon=True).start()
    return jsonify({"status": "shutting_down", "message": "De applicatie wordt afgesloten..."})
```

Key details:
- The cancel-all call goes directly to the backend on port 8010 (not through the frontend proxy) since it's server-to-server
- If the backend call fails, we log and continue — shutdown should never be blocked
- `os._exit(0)` is used to force exit since `sys.exit()` may be caught by Flask
- The response is sent before the shutdown begins (threading)

## Frontend: shutdown button

**Location:** Location of the button is bottom left corner. For style, check hte wireframe in `ai/wireframes/shutdown.html`.

**Behavior:**
1. User clicks "Afsluiten"
2. Show a confirmation dialog:
    - Default message: "Weet u zeker dat u de applicatie wilt stoppen?"
    - If an analysis is running (check current state): "Er is momenteel een analyse actief. Deze wordt gestopt als u verdergaat."
    - Buttons: "Stoppen" (primary/red) and "Annuleren" (secondary)
3. On confirm: call `POST http://localhost:9090/shutdown`
4. On success: show a full-screen message: "De applicatie is afgesloten. U kunt dit venster sluiten."
5. On error: show an error message: "Er is een fout opgetreden bij het afsluiten. Sluit het venster en probeer het opnieuw."

**Angular implementation notes:**
- The shutdown call goes to the agent (port 9090), not the backend. This needs to be configured in the Angular proxy or called directly.
- After shutdown, the backend will become unreachable — the frontend should not try to make further API calls.
- The confirmation dialog should use whatever dialog/modal component is already used in the app.

For the frontend wireframe, refer to: `ai/wireframes/shutdown.html`

## No changes needed

- **StartupOrchestrator** — no changes. The startup flow doesn't use the shutdown endpoint.
- **_kill_previous_agent** — no changes. The startup kill is separate from the user-initiated shutdown.
- **Docker Compose** — no changes.

# Testing Notes

- Start the app, run an analysis, click "Afsluiten" while the analysis is running. Verify the analysis is marked CANCELLED in the database.
- Start the app with no running analyses, click "Afsluiten". Verify it shuts down cleanly (cancel-all returns 0 cancelled).
- Start the app, manually stop the backend container, then click "Afsluiten". Verify the agent logs a warning about the backend being unreachable but still proceeds with docker compose down.
- After shutdown, verify no Docker containers are running (`docker ps`).
- After shutdown, verify the agent process is no longer running.
- Restart the app after a shutdown. Verify Phase 4 finds no leftover containers (shutdown cleaned them up). Verify previously running analyses show CANCELLED status in the UI.
- Test the confirmation dialog — clicking "Annuleren" should not trigger shutdown.
- Test with multiple analyses running — all should be cancelled.