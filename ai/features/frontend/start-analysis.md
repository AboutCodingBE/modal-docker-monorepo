Implement the frontend for triggering AI analysis on an archive. Use the wireframe at `ai/wireframes/start-analysis.html`
as a reference. 

## Analysis Modal

When the user clicks "Start Analysis" on an archive card,
show a modal dialog with:

1. Title: "Analyse starten voor <archive name>"

2. A list of available analysis types. For now only one:
    - Summary (Samenvatting)
      Each type has a checkbox to select it and a dropdown
      to choose the model. Default model: gemma3:1b

3. A "Start" button that is disabled until at least one
   analysis type is selected

4. A "Cancel" button to close the modal

When the user clicks Start, send:
POST /api/analysis/start
{
"archiveId": "uuid",
"analysis": [
{ "type": "summary", "model": "gemma3:1b" }
]
}

The response returns the created task IDs. Close the modal
and show the progress pipeline on the archive card.

## Archive Card Updates

The archive card should show different states:

1. No analysis running, no results:
   Show "Analyse Starten" button

2. Analysis running:
   Show a pipeline stepper with progress:
    - Step name (e.g., "Samenvatting")
    - Progress bar with percentage
    - Files processed / total
    - Current file name
      Subscribe to SSE at
      GET /api/analysis/tasks/{task_id}/progress

3. Analysis completed:
   Show "Resultaten" button and "ANALYSED" badge
   Optionally show which analyses have been run

4. Analysis failed:
   Show error state with "Opnieuw proberen" (retry) button

## On page load

When the archive overview page loads, call
GET /api/analysis/tasks/active to check for any running
tasks. For each running task, show the progress pipeline
on the corresponding archive card and subscribe to its
SSE stream.

## Available models

For now hardcode the available models in the frontend:
- gemma3:1b (default)

Later this will come from a backend endpoint or database
configuration. Keep the model selection in a separate
component so it's easy to make dynamic later.

## Component structure

- AnalysisModalComponent — the modal dialog with analysis
  type selection and model dropdowns
- AnalysisPipelineComponent — the stepper/progress view
  that shows on the archive card during processing
- Keep these in a shared or analysis feature folder so
  they can be reused on the archive detail page later