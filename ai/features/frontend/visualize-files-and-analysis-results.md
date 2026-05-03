Implement the archive detail browser with file list and
analysis results. Reference the uploaded wireframe
(browser-files-as-list.html.html) for the exact layout and styling.

The archive detail page has 3 panes:

## Pane 1 — Archive Summary (already exists)
No changes needed. Shows total files, file types, folders,
and mime type tags.

## Pane 2 — Archive Browser (update needed)
The existing folder browser needs a new section: a file
table below the folder grid.

Structure:
- Breadcrumb navigation (already exists)
- File count summary: "📄 X bestanden direct in deze map"
- Subfolder grid (already exists)
- Horizontal divider
- Files table section:
    - Label: "BESTANDEN IN DEZE MAP (X VAN Y)" showing
      filtered vs total count
    - Toolbar with search input ("Zoek op bestandsnaam...")
      and type filter dropdown ("Alle types")
    - Scrollable table (max-height 320px) with columns:
        - Bestandsnaam (bold)
        - Type (monospace, from Tika mime type)
        - Grootte (file size, formatted as KB/MB)
    - Clicking a row selects the file (highlighted in blue)

Data source:
GET /api/archives/{archive_id}/folder/{folder_id}/files
This returns files with name, mime_type, and size_bytes.

The search filters by filename, the dropdown filters by
mime type. Both filter client-side on the loaded data.

## Pane 3 — Context-Dependent Detail Panel

This pane switches between two views based on whether
a file or folder is selected.

### Folder View (default)
Shows when no file is selected or when navigating folders.
- Title: "Inhoud huidige map"
- Scope indicator: "Resultaten voor: /path"
- Two stat cards in a row:
    - "Bestanden in deze map" with count
    - "Bestandstypen" with count
- File type grid: cards showing each mime type with count
- Horizontal divider
- Summary section:
    - Title: "Samenvatting"
    - Summary block with grey background containing:
        - Label: "AI-GEGENEREERDE SAMENVATTING VAN DEZE MAP"
          with model badge (e.g., "gemma3:1b" in monospace)
        - Summary text below
        - If no summary: italic "Geen samenvatting beschikbaar
          voor deze map."

Data source for summary:
GET /api/archives/{archive_id}/analysis/{folder_id}

### File View
Shows when a file is clicked in the table.
- Header with "Bestandsdetails" title and "← Terug naar map"
  button on the right
- File name in a grey header box
- Three metadata cards in a row:
    - Type (mime type)
    - Grootte (file size)
    - Map (current folder path)
- Horizontal divider
- Summary section:
    - Title: "Samenvatting"
    - Summary block with grey background containing:
        - Label: "AI-GEGENEREERDE SAMENVATTING VAN DIT BESTAND"
          with model badge
        - Summary text below
        - If no summary: italic "Geen samenvatting beschikbaar."

Data source for summary:
GET /api/archives/{archive_id}/analysis/{file_id}

Clicking "← Terug naar map" deselects the file and shows
the folder view again.

## Component structure
- FileTableComponent — the searchable/filterable file list
- FileDetailComponent — the file metadata + analysis view
- FolderDetailComponent — the folder stats + analysis view
- AnalysisSummaryComponent — reusable block that shows the
  AI summary with model badge, used by both file and folder
  detail components

## Important notes
- The file table and detail panel are in Pane 2 and Pane 3
  respectively — they are separate panels, not one component
- When navigating to a different folder, reset the file
  selection and show the folder view in Pane 3
- The analysis data is fetched separately from the metadata
  (as discussed) — the summary component makes its own API
  call when the selected file/folder changes
- Format file sizes: bytes to KB/MB with appropriate rounding
- The model badge should show the actual model name from the
  analysis response, not hardcoded