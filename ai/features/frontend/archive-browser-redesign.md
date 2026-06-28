# Use Case

Redesign the archive detail / browser page in the Angular frontend. The new layout puts the archive summary at the top, followed by a side-by-side view with the file browser on the left and a context-sensitive detail panel on the right. The file table shows categories instead of mime types. The detail panel has tabs for summaries and NER results.

The input of this use case:
User navigates to an archive's detail page from the archive overview.

Input mechanism of this use case:
Existing Angular routing — no URL changes needed.

The output of this feature:
A completely redesigned archive detail page matching the wireframes provided.

## Wireframes

The following wireframes are available for reference:
- **Main layout wireframe:** `ai/wireframes/archive-browser-update.html` — shows the full page layout with pane 1 (archive summary), pane 2 (file browser), and pane 3 (detail panel)
- **NER tab wireframe:** `ai/wireframes/archive-browser-update-ner-tabs.html` — shows the NER tab content for both files and folders, including color-coded entity tags

# Layout Overview

The page has three main areas stacked vertically:

## Pane 1: Archive summary (top, full width)
A compact panel showing:
- **Left side — stats:** three stat blocks showing Bestanden (file count), Types (distinct category count), Mappen (folder count)
- **Right side — AI summary:** the archive's root folder summary text, with a label "Archief samenvatting" and a model tag (e.g. `gemma3:1b`)
- These are separated by a vertical border

## Pane 2 + 3: Side-by-side layout (below pane 1)

### Pane 2: File browser (left, flexible width)
- **Breadcrumbs** — showing current path, clickable to navigate up
- **File count** — "📄 X bestanden direct in deze map"
- **Subfolder chips** — labeled "X submappen", each subfolder as a clickable chip with 📁 icon
- **Divider**
- **File table** — with header "Bestanden in deze map (X van Y)"
    - Mini toolbar: search input ("Zoek op bestandsnaam...") + category filter dropdown ("Alle types")
    - Scrollable table with columns: Bestandsnaam, Categorie, Grootte
    - Clicking a row selects it (highlighted with blue background) and populates the detail panel
    - Clicking a subfolder chip navigates into that folder

### Pane 3: Detail panel (right, fixed width ~320px)
Context-sensitive — shows either file detail or folder detail, never both.

**When a file is selected:**
- Header: file name + "Bestand" badge
- Two tabs: Samenvatting, NER
- **Samenvatting tab:** AI-generated summary with model tag label "AI-gegenereerde samenvatting"
- **NER tab:** entities grouped by category (see NER section below)

**When a folder is clicked (subfolder chip):**
- Header: folder name with 📁 icon + "Map" badge
- Two tabs: Overzicht, Samenvatting
- **Overzicht tab:** stats (Bestanden, Types) + file category chips with counts
- **Samenvatting tab:** folder AI summary with model tag

**Default state (nothing selected):**
- Show a placeholder message like "Selecteer een bestand of map om details te bekijken"

# NER Tab Content

## File NER tab
Entities are grouped by category with color-coded tags. No counts per entity (individual files).

**Sections in order:**
1. **Personen** — blue tags (`background: #dbeafe`, `border: #bfdbfe`, `color: #1e40af`)
2. **Locaties** — green tags (`background: #dcfce7`, `border: #bbf7d0`, `color: #166534`)
3. **Organisaties** — yellow/amber tags (`background: #fef3c7`, `border: #fde68a`, `color: #92400e`)
4. **Overige** — purple tags for dates/misc (`background: #f3e8ff`, `border: #e9d5ff`, `color: #6b21a8`)

Each section has an uppercase label (font-size 9px, weight 700, letter-spacing 0.06em, color #6b7280).

At the bottom: "**X** entiteiten gevonden in dit bestand" (grey text, with a top border separator).

Empty sections (no entities of that type) should be hidden entirely.

## Folder NER tab
Not implemented yet — folder NER aggregation is a future feature. Do NOT show a NER tab for folders in this phase.

# Data Sources

All backend endpoints are ready. Here's what to call:

## Pane 1: Archive summary
- **Stats:** from the existing folder contents endpoint `GET /api/archives/{id}/folder?path=/`
    - `direct_file_count` for file count at root level. Note: for the total archive file count, you may need a separate source or sum across all folders
    - `categories` array for distinct category count (count of distinct categories)
    - Subfolder count from `subfolders` array length
- **Summary:** from the existing summary endpoint (however summaries are currently fetched — the root folder's summary)

## Pane 2: File browser
- **Folder structure:** `GET /api/archives/{id}/folder?path=/{path}` — returns subfolders, file count, categories, mime_types
- **File list:** `GET /api/archives/{id}/folder/{folder_id}/files` — returns individual files with `name`, `extension`, `size_bytes`, `mime_type`, `category`
- The `category` field is new (just added in Phase 1b) and replaces `mime_type` as the displayed column

## Pane 3: Detail panel
- **File summary:** from the existing summary endpoint for individual files
- **File NER:** `GET /api/archives/{id}/files/{file_id}/ner` (new endpoint from Phase 2)
    - Returns: `persons`, `locations`, `organisations`, `misc` arrays + `total_entities`
- **Folder overview stats:** from `GET /api/archives/{id}/folder?path=/{folder_path}` — reuse the folder contents data
- **Folder summary:** from the existing summary endpoint for folders

# Business Rules

## File table
- The category column shows the `category` value from the files endpoint (e.g. "tekstbestand", "beeldbestand")
- File size should be formatted human-readable (KB, MB, GB)
- The search input filters files by name (client-side filtering is fine for the current scale)
- The category filter dropdown is populated with the distinct categories from the current folder's files
- "Alle types" is the default filter option showing all files
- Selected row has light blue background (`#eff6ff`) and blue text for the filename

## Detail panel
- Only one panel content is shown at a time — file OR folder, not both
- When a file is selected and then a subfolder is clicked, the panel switches to folder view
- When navigating into a subfolder, the detail panel resets (no selection)
- NER data is fetched lazily — only when the user clicks the NER tab, not on file selection
- Summary data can be fetched on file/folder selection (it's lightweight)
- If no summary exists for a file/folder, show "Geen samenvatting beschikbaar" in the Samenvatting tab
- If no NER results exist for a file, show "Geen NER resultaten beschikbaar" in the NER tab

## Navigation
- Clicking a breadcrumb segment navigates to that folder level
- Clicking a subfolder chip navigates into that subfolder and updates breadcrumbs
- The "← Overzicht" button navigates back to the archive list
- When navigating folders, the detail panel resets to its default/placeholder state

# Design System

- Background: `#f0f2f5`
- Panel background: `#fff` with `border: 1px solid #e5e7eb`, `border-radius: 10px`, `box-shadow: 0 1px 4px rgba(0,0,0,0.05)`
- Primary blue: `#3b6ef5`
- Text primary: `#111827`
- Text secondary: `#6b7280`
- Font: system font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
- Stat values: `font-size: 20px`, `font-weight: 700`
- Stat labels: `font-size: 9px`, `font-weight: 600`, `text-transform: uppercase`, `letter-spacing: 0.06em`
- Model tag: monospace font, `background: #e5e7eb`, `border: 1px solid #d1d5db`, `border-radius: 3px`, `padding: 0px 5px`, `font-size: 9px`
- Tabs: `font-size: 12px`, active tab has blue bottom border and blue text (`#3b6ef5`)
- Table headers: `font-size: 10px`, `font-weight: 700`, uppercase, sticky
- Table rows: `font-size: 13px`, hover background `#f9fafb`

### NER tag colors
- **Personen:** `background: #dbeafe`, `border: #bfdbfe`, `color: #1e40af`
- **Locaties:** `background: #dcfce7`, `border: #bbf7d0`, `color: #166534`
- **Organisaties:** `background: #fef3c7`, `border: #fde68a`, `color: #92400e`
- **Overige:** `background: #f3e8ff`, `border: #e9d5ff`, `color: #6b21a8`

# Component Structure Suggestion

This is a suggestion — adapt to the existing Angular component structure:

- **ArchiveDetailComponent** — main page, orchestrates pane 1, 2, 3
- **ArchiveSummaryComponent** — pane 1 (stats + AI summary)
- **FileBrowserComponent** — pane 2 (breadcrumbs, subfolders, file table)
- **DetailPanelComponent** — pane 3 wrapper (switches between file and folder detail)
    - **FileDetailComponent** — file tabs (Samenvatting, NER)
    - **FolderDetailComponent** — folder tabs (Overzicht, Samenvatting)
    - **NerTagsComponent** — reusable component for rendering color-coded NER entity tags (used in file NER tab, and later in folder NER tab)

# No changes needed

- **Backend endpoints** — all ready (folder contents with categories, file list with category, file NER, summaries)
- **Routing** — existing routes work
- **Sidebar** — already exists, no changes
