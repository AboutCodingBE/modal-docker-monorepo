# Feature Context — Flat NER/topic index tables (`file_entities`, `file_topics`)

Phase 1 of 3 for the hierarchical/list views feature (see `feature-context-list-view-file-listing.md`
for phase 2). Ships independently — useful on its own for future visuals/aggregates, not gated on
phase 2 or 3 existing.

## Problem this solves

NER and topic results currently live only as JSONB, tied to a file's most-recent-completed analysis
(per the existing "most recent" convention: `WHERE archive_id = X AND type = Y AND status =
'COMPLETED' ORDER BY analyzed_at DESC LIMIT 1`). There's no queryable "list of distinct entities/topics
in this archive" today — answering that requires scanning every file's JSONB at query time.

This matters concretely for phase 3 (topic/NE filtering on the file list): filtering by entity needs
an autocomplete ("type 'Jan', get matching entity suggestions") and a "which files match" query, both
of which need to be fast against archives with potentially hundreds of distinct entities — not
practical to build well against raw per-file JSONB blobs.

The archive-level aggregate endpoints (`get_ner_for_folder`/`get_topics_for_folder`) were considered
as a source for this instead, but they return a **curated, capped** list (confirmed), not the full
distinct set — fine for a "Samenvatting"-style overview, not sufficient as a filter/autocomplete
backend, since it can't answer "does this less-prominent entity exist anywhere in the archive."

## Schema

Two separate flat tables, mirroring the existing split between `ner` and `topic_detection` (not one
merged/polymorphic table — entities have a type facet topics don't, so a shared table would need a
nullable discriminator column for no real benefit):

```sql
CREATE TABLE file_entities (
    id UUID PRIMARY KEY,
    file_id UUID NOT NULL,
    archive_id UUID NOT NULL,
    ner_id UUID NOT NULL,          -- FK to the specific ner row this came from, see cascade note below
    entity_text VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,  -- PERSON, ORG, LOCATION, etc.
    CONSTRAINT file_entities_ner_id_fkey FOREIGN KEY (ner_id) REFERENCES ner(id) ON DELETE CASCADE
);
CREATE INDEX idx_file_entities_archive ON file_entities (archive_id);
CREATE INDEX idx_file_entities_text ON file_entities (entity_text);

CREATE TABLE file_topics (
    id UUID PRIMARY KEY,
    file_id UUID NOT NULL,
    archive_id UUID NOT NULL,
    topic_detection_id UUID NOT NULL,  -- FK to the specific topic_detection row, see cascade note below
    topic_label VARCHAR NOT NULL,
    CONSTRAINT file_topics_topic_detection_id_fkey FOREIGN KEY (topic_detection_id)
        REFERENCES topic_detection(id) ON DELETE CASCADE
);
CREATE INDEX idx_file_topics_archive ON file_topics (archive_id);
CREATE INDEX idx_file_topics_label ON file_topics (topic_label);
```

`archive_id` is denormalized onto both tables (same pattern already used elsewhere, e.g. `TikaAnalysis
.mime_type` feeding archive-level stats) — a file's archive membership never changes, so there's no
drift risk, and it avoids joining through `files` for every archive-scoped query (`WHERE archive_id = X
GROUP BY entity_text`, etc.).

## Cascade behavior — the part that matters most

FK'ing to `ner_id`/`topic_detection_id` (not just `file_id`) is the key design choice here, so that
**redo analysis wipes these rows for free**, using the exact same mechanism already relied on
elsewhere: deleting an `archive_analysis` row cascades to `ner`/`topic_detection` via `analysis_id`,
which in turn cascades to `file_entities`/`file_topics` via `ner_id`/`topic_detection_id`. No new
cleanup code needed in the redo-analysis flow — it's an extension of a chain that already exists,
not a parallel deletion path to remember and keep in sync.

If these tables FK'd to `file_id` instead, redoing NER on a file would leave stale index rows behind
(old entities from the superseded analysis), since nothing about redo touches `file_id` directly —
exactly the kind of thing that becomes a quiet stale-data bug later. Explicitly avoided by this design.

## Write path

Populated as a side effect wherever NER/topic results are currently written (alongside the existing
JSONB write, not instead of it — JSONB remains the source of truth for display; these tables are a
query-optimized index of the same data). One bulk insert per file, sized to however many
entities/topics that file's analysis produced (typically small — tens of rows at most).

**Performance impact: expected to be negligible.** The dominant per-file cost is the analysis itself
(spaCy inference or an LLM call via Ollama — hundreds of milliseconds to multiple seconds), against
which a single extra bulk-insert batch (single-digit milliseconds) is effectively rounding error. Not
benchmarked against the real pipeline yet — worth a quick sanity check (time a representative NER call
today, compare to a mocked ~30-row bulk insert against the actual DB) before assuming this holds, but
there's no reason to expect otherwise given the relative costs involved.

## Backfill — open question, needs a decision

These tables don't exist yet, so every already-analyzed file has no index rows until one of:
- A one-time backfill script reads existing `ner`/`topic_detection` JSONB and populates the new tables
  retroactively, or
- Historical archives simply don't show up in entity/topic filtering until someone re-runs analysis on
  them (accepted gap, not fixed).

Needs an explicit decision before/at implementation — not addressed by this context yet.

## Files affected (expected, to confirm against actual code)

- Wherever `ner`/`topic_detection` rows are currently inserted (NER-via-spaCy path, NER-via-LLM path,
  topic detection) — each needs the additional bulk insert into `file_entities`/`file_topics`.
- Migration for the two new tables + indexes.

## Not in scope here

- Any querying/autocomplete/filtering UI against these tables — that's phase 3, and depends on this
  phase existing first.
- Changes to the existing JSONB storage or the `get_ner_for_folder`/`get_topics_for_folder` aggregate
  endpoints — both continue to work exactly as they do today; this is a new, parallel index, not a
  replacement.