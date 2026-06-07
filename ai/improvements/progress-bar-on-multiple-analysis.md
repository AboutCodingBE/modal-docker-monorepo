# Progress Bar: Sequential SSE Subscriptions for Multiple Analyses

## Problem

When multiple analyses are started (e.g. Summary + NER), the backend runs them
sequentially. The frontend however opens SSE connections for **all** task IDs at
once. This causes the progress display to flicker between the running task
(e.g. 30%) and the not-yet-started task (0% / 0 of 0 files), because both
streams emit events concurrently and the last one received wins.

The same problem occurs when the user navigates away and returns to the archive
browser — `loadAndTrack()` is called in `ngOnInit` and re-subscribes to all
active tasks at once.

---

## Root Cause

**On analysis start** (`archive-browser.ts / onAnalysisStarted`):
`taskProgress.track()` is called for every returned `taskId` immediately. The
second task is in `pending` state and keeps emitting zeroed-out events every
second, overwriting the real progress of the first task.

**On navigate-back / page reload** (`archive-browser.ts / ngOnInit`):
`taskProgress.loadAndTrack()` fetches all active tasks and subscribes to all of
them at once. Additionally:
- The `analysisTaskIds` set is empty on reload, so AI analysis tasks are
  incorrectly treated as Tika tasks (shown as a percentage bar instead of the
  analysis pipeline).
- The `AnalysisTask` model has no `created_at` field and `get_active_tasks`
  orders by `started_at DESC NULLSLAST` — pending tasks have no `started_at`,
  so their order is indeterminate. We cannot reliably know which task should run
  first.
- There is no `task_type` field to tell Tika tasks apart from AI analysis tasks.

---

## Proposed Fix

### Part 1 — Analysis start (frontend only)

Only open an SSE connection for the **currently active** task. When that task
completes or fails, open the connection for the next task in the queue.

#### 1a. Add a per-archive task queue to `archive-browser.ts`

```ts
private taskQueues = new Map<string, string[]>();
```

Keyed by `archiveId`. Holds task IDs not yet subscribed to SSE.

#### 1b. Update `onAnalysisStarted` in `archive-browser.ts`

Register all task IDs in `analysisTaskIds` (so the update handler recognises
them), but only open SSE for the **first** task — queue the rest.

```ts
onAnalysisStarted(event: { archiveId: string; taskIds: string[] }): void {
  for (const taskId of event.taskIds) {
    this.analysisTaskIds.add(taskId);
  }

  if (event.taskIds.length > 0) {
    this.taskProgress.track(event.archiveId, event.taskIds[0]);
    this.taskQueues.set(event.archiveId, event.taskIds.slice(1));
  }

  this.archives.update(list =>
    list.map(a =>
      a.id === event.archiveId ? { ...a, status: 'in_progress' as const } : a
    )
  );
}
```

#### 1c. Dequeue next task on completion in `_subscribeToUpdates` of `archive-browser.ts`

Inside the `isAiAnalysis` branch, after updating archive state, add:

```ts
if (isCompleted || isFailed) {
  const queue = this.taskQueues.get(update.archiveId) ?? [];
  if (queue.length > 0) {
    const [nextTaskId, ...rest] = queue;
    this.taskQueues.set(update.archiveId, rest);
    this.taskProgress.track(update.archiveId, nextTaskId);
  } else {
    this.taskQueues.delete(update.archiveId);
  }
}
```

---

### Part 2 — Navigate-back / reload (backend + frontend)

This requires a small backend change to expose the information the frontend needs
to reconstruct the queue.

#### 2a. Add `created_at` and `task_type` to `AnalysisTask` model (`shared/models.py`)

```python
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
task_type:  Mapped[str] = mapped_column(String(20), nullable=False, default="analysis")
```

`task_type` values: `"tika"` for Tika ingestion tasks, `"analysis"` for AI
analysis tasks.

#### 2b. Migration

Add a new Alembic migration that:
- Adds `created_at` column (default `now()`)
- Adds `task_type` column (default `'analysis'`)
- Backfills existing rows: set `task_type = 'tika'` for tasks linked to an
  archive whose `tika_task_id` matches the task id (or simply leave all
  existing rows as `'analysis'` if backfill is not worth the complexity)

#### 2c. Update `task_tracker.create_task()` to accept `task_type`

```python
async def create_task(
    session: AsyncSession,
    archive_id: uuid.UUID,
    total_files: int,
    task_type: str = "analysis",
) -> AnalysisTask:
```

Update callers:
- `start_router.py` — pass `task_type="analysis"` (already the default, no
  change needed)
- Tika ingestion code — pass `task_type="tika"`

#### 2d. Update `get_active_tasks` ordering in `task_tracker.py`

Order by `created_at ASC` so tasks come back in the order they were created,
giving a deterministic queue:

```python
.order_by(AnalysisTask.created_at.asc())
```

#### 2e. Expose `created_at` and `task_type` in the active tasks endpoint (`router.py`)

```python
"created_at": task.created_at.isoformat() if task.created_at else None,
"task_type": task.task_type,
```

#### 2f. Update `ActiveTask` interface in `task-progress.service.ts`

```ts
export interface ActiveTask {
  ...
  created_at: string | null;
  task_type: string;
}
```

#### 2g. Refactor `TaskProgressService` — expose tasks instead of auto-subscribing

Change `loadAndTrack()` to return `Observable<ActiveTask[]>` instead of
subscribing internally. This lets `archive-browser` apply the same queue logic.

```ts
getActiveTasks(): Observable<ActiveTask[]> {
  return this.http.get<ActiveTask[]>('/api/analysis/tasks/active');
}
```

Remove the current `loadAndTrack()` method (or keep it for Tika-only tasks if
needed).

#### 2h. Update `archive-browser.ngOnInit` to apply queue logic on reload

Replace `this.taskProgress.loadAndTrack()` with a call to `getActiveTasks()`:

```ts
this.taskProgress.getActiveTasks().subscribe(tasks => {
  for (const task of tasks) {
    // Emit snapshot immediately
    this.taskProgress.emitSnapshot(task);

    if (task.task_type === 'analysis') {
      this.analysisTaskIds.add(task.task_id);
    }
  }

  // Group analysis tasks per archive, sorted by created_at (already ordered by backend)
  const byArchive = new Map<string, ActiveTask[]>();
  for (const task of tasks.filter(t => t.task_type === 'analysis')) {
    const list = byArchive.get(task.archive_id) ?? [];
    list.push(task);
    byArchive.set(task.archive_id, list);
  }

  for (const [archiveId, archiveTasks] of byArchive) {
    // Subscribe to the first (running or earliest pending), queue the rest
    this.taskProgress.track(archiveId, archiveTasks[0].task_id);
    this.taskQueues.set(archiveId, archiveTasks.slice(1).map(t => t.task_id));
  }

  // Tika tasks: subscribe immediately as before
  for (const task of tasks.filter(t => t.task_type === 'tika')) {
    this.taskProgress.track(task.archive_id, task.task_id);
  }
});
```

`emitSnapshot` is a new small method on `TaskProgressService` that emits an
initial snapshot event for a task (extracted from the current `loadAndTrack`
logic).

---

## Summary of files changed

| File | Change |
|------|--------|
| `backend/app/shared/models.py` | Add `created_at`, `task_type` to `AnalysisTask` |
| `backend/app/analysis/task_tracker.py` | Accept `task_type` in `create_task`, reorder `get_active_tasks` |
| `backend/app/analysis/router.py` | Expose `created_at`, `task_type` in active tasks response |
| `backend/migrations/versions/0006_...py` | New migration for the two new columns |
| Tika ingestion (task creation call site) | Pass `task_type="tika"` |
| `frontend/.../task-progress.service.ts` | Replace `loadAndTrack` with `getActiveTasks` + `emitSnapshot`, expose `ActiveTask` with new fields |
| `frontend/.../archive-browser.ts` | Add `taskQueues`, update `onAnalysisStarted`, `_subscribeToUpdates`, `ngOnInit` |
