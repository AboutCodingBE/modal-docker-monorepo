# Feature Context — Literal text search over document content

Backend/query layer only. UI is covered separately (wireframe).

## What this is

A search that finds files whose extracted text (`tika_analyses.content`) contains the text the user
typed, matched literally and case-insensitively. This is deliberately the simple version: substring
matching, no ranking, no stemming, no semantic matching. Semantic search is a separate sibling feature
(it already has its own wireframes). This feature should return the same per-file properties and plug
into the same kind of results view; the only difference is how matches are found.

## Why plain ILIKE is enough (measured)

The query is a case-insensitive substring match on `tika_analyses.content`, always scoped by
`archive_id`. Because the scope is one archive (up to roughly 10k files, largest seen so far ~3k),
the unindexed scan only touches that archive's documents. Tested against a real archive: performs well
with no extra index. No tsvector column and no trigram index are needed for this feature.

**Re-check on the largest archive** (the ~10k-file ceiling) with `EXPLAIN ANALYZE` before calling this
done, since testing so far was likely on smaller ones. If it is ever too slow, the fix that does not
change the query is a trigram index:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_tika_content_trgm ON tika_analyses USING GIN (content gin_trgm_ops);
```

Not part of this feature. Only add it if measurements say so (it helps for search terms of 3+
characters, costs index size and slower inserts).

## Query

```sql
SELECT f.id, f.name, f.relative_path, ...
FROM files f
JOIN tika_analyses t ON t.file_id = f.id
WHERE f.archive_id = :archive_id
  AND f.is_directory = false
  AND t.content ILIKE '%' || :term || '%'
```

In SQLAlchemy, do not hand-build the pattern:

```python
TikaAnalysis.content.icontains(term, autoescape=True)
```

Requirements:
- **Bound parameter only.** Never interpolate the user's text into the SQL string (SQL injection).
- **Escape wildcards.** `%` and `_` typed by a user must be treated as literal characters, which
  `autoescape=True` handles. Without it, searching for `100%` or `TAAK_2` would behave as a wildcard
  pattern.
- **Never select `content` into the response.** It is a large column (stored out of line). Select only
  the file/metadata columns the list needs, otherwise every result row drags full document text across
  the wire.

## Snippets and click behaviour (to match semantic search, minus the score)

Semantic search results show snippets per file, and clicking leads to the file's details or its full
text. Literal search does the same. The one thing it does not have is a match score: a literal match
is yes or no.

- **Snippet:** a short passage of the extracted text around an occurrence of the search term, with the
  matched text marked. Locate occurrences case-insensitively, the same way the `WHERE` condition
  matches.
- **Compute snippets only for the files on the current page of results**, never in the main query.
  `content` is a large column, so do it as a second step after the page of file ids is known.
- **Cap the work:** a maximum number of snippets per file and a maximum snippet length. The semantic
  search wireframe shows two snippets per file; use the same cap unless the semantic endpoint says
  otherwise.
- **Overlay position:** clicking a snippet opens an overlay with the full text. For the overlay to
  open at the right place, the response needs the match position (for example a character offset into
  `content`). Check what the semantic search endpoint returns for this and use the same field, so one
  overlay implementation serves both. The full text itself is already available through
  `GET /api/files/{id}/content`.
- **No match indicator.** Semantic search shows a similarity score ("97% match"); literal search has
  nothing equivalent, so the field is omitted from the response and the UI shows no match label. A file
  is either in the results or it is not.
- **Click behaviour, same as semantic search:**
    - Clicking the filename opens the file's details in the shared side panel (Overzicht, Samenvatting,
      NER, Topics), driven by the file `id`. Nothing new to build on the backend for this.
    - Clicking a snippet opens the full text of the file, positioned at that match (see "Overlay
      position" above).

## Matching semantics (what "literal" means here)

- Case-insensitive substring match. "karl BETAALT" matches "Karl betaalt". "jans" matches "Jansen".
- The input is matched as one exact phrase, words adjacent, in order, single spaces.
- **Not matched:** different word order, words that are not adjacent, accents ("Jan" will not match
  "Ján"), and a phrase that is split across a line break in the extracted text.
- Line breaks matter: Tika output from PDFs and scans often contains a newline in the middle of a
  sentence, so a phrase that reads as continuous on the page can have `\n` between its words in
  `content` and will not match.
- No ranking. Results are ordered by whatever sort the caller picks (path/date/category), not by
  relevance.

## Integration: its own endpoint and feature (decided)

Search is a separate feature with its own endpoint, not an extra filter on `list_files`. Users will
experience it as its own thing (a search box leading to a results view), and a dedicated endpoint
leaves room for a result shape that differs from the file list (for example snippets later).

Suggested shape (names to be settled during implementation):

```
GET /api/archives/{archive_id}/search?q=...&folder_path=...&cursor_id=...&cursor_value=...
```

- **Own feature folder**, per the monorepo convention (one folder per feature, e.g.
  `search_files_for_archive/` with its own router and repository).
- **Response rows: same properties as the semantic search results.** Both features should return the
  same per-file properties, so the UI can render them with the same results view, the same file-click
  behaviour (side panel) and the same snippet overlay. The reference is the semantic search endpoint:
  mirror its response shape field for field, not the list view's, leaving out the match score. From the
  semantic search wireframe, a result is: filename, relative path, and a list of snippets (matched terms
  highlighted), plus the file `id` for the side panel. Never include the full `content` in the response.
- **Ordering:** there is no relevance ranking, so use a stable, deterministic default: order by
  `relative_path`, with `file.id` as the tiebreaker.
- **Pagination:** cursor (keyset) pagination, the same pattern as `list_files`, keyed on
  `(relative_path, id)`. Do not copy-paste the cursor helper from `list_files` into a second place.
  This project has already had to consolidate duplicated `ArchiveAnalysisRepository` and
  `ollama_client.py` copies into `app/shared/`; if the keyset condition builder is needed in both
  features, extract it to a shared module instead of letting a second copy appear.
- **Scope:** `archive_id` is required. `folder_path` is optional and follows the same prefix rule as the
  list endpoint (`{prefix}/%`). No `folder_path` searches the whole archive.
- **Other filters:** none in this version (no klasse, taal, entity or topic filters on search results).
  A search is a search. If combining them is wanted later, the existing condition-building code can be
  reused.

## Behaviour to specify

- **Empty or whitespace-only `q`:** return an empty result (or a 400), do not treat it as "match
  everything with a wildcard". Decide which.
- **Pagination:** any change to `q` or `folder_path` is a different query, so the client restarts from
  page 1, same rule as every other filtered listing.
- **Folder scope:** search from the root searches the whole archive; search inside a folder searches
  that subtree.
- **Files with no extracted text** (no `tika_analyses` row, or NULL/empty `content`, e.g. images without
  OCR) can never match a search. They are simply excluded when `q` is set. This is expected, not a bug,
  but worth knowing since OCR is off by default per archive.
- **Minimum term length:** not enforced by this version. Short terms (1-2 characters) will match a
  large share of documents. Decide whether the UI or the API should require a minimum (e.g. 2-3
  characters).

## Explicitly out of scope

- Ranking by relevance, stemming, stop words (that would be the tsvector approach).
- Accent-insensitive matching.
- Tolerating line breaks and irregular whitespace inside a phrase.
- Fuzzy / typo-tolerant matching.
- Semantic search.

## Open questions

- **Multi-word input:** this context specifies exact-phrase behaviour (the literal reading). The
  alternative is "all words anywhere in the document" (split on whitespace, AND the terms). Many users
  expect the second from a search box. Decide which one this version does; it is a small change either
  way.
- **Whitespace/line-break tolerance:** whether to normalize whitespace so a phrase still matches across
  a line break (e.g. a regex with `\s+` between words, or normalizing `content` at write time). Not
  needed for a first version, but likely to surface in real use on scanned/PDF documents.
- **Occurrence count:** not included. If users later want to see how many times a term appears in a
  file, it can be added cheaply for the files on the current page (counted in the same pass as the
  snippets), but it would be display-only, not a sort key.
- **Combining with the metadata/entity/topic filters:** not in this version; revisit if users ask for it.
- **Minimum term length** (see above).