The SSE progress system has a problem: when the user navigates
away from the overview page, the EventSource closes and progress
is lost when returning. Fix this:

1. Add endpoint: GET /api/analysis/tasks/active
   Returns all tasks with status "running" or "pending".
   Include archive_id, task_id, task_type, total_files,
   processed, percentage, status.

2. On the archive overview page (archive card list), on
   component init, call /api/analysis/tasks/active. For each
   running task, show the progress bar on the corresponding
   archive card and subscribe to its SSE stream for live updates.

3. When the user navigates away and comes back to the overview
   page, the component re-fetches active tasks and re-subscribes
   to SSE streams. The SSE connection should be managed in a
   service, not directly in the component.

4. Key point: the initial state comes from the REST endpoint
   (shows current progress immediately on page load). The SSE
   stream provides live updates after that. So even if there is
   a brief gap between navigation and reconnection, the user
   always sees the latest progress on the archive cards.

5. When a task completes (SSE sends status "completed"), update
   the archive card to show the completed state and close the
   SSE connection for that task.