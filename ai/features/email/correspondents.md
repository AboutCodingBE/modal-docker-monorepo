# Feature Context — Email correspondents (KAN-85)

Backend/data layer only. UI is covered separately (wireframe).

**Status: active again.** It was on hold over how to show the data. Decided: show it in the file
overview, only for files that have correspondents. This document replaces the earlier on-hold version
and restates everything needed, so it does not depend on that file.

## Goal

Extract the sender and recipients (To, CC, BCC) from email files at ingestion, store them, and make
them available for the file overview. Non-email files get no rows.

## Current state

1. `tika_extract_correspondents()` exists but is never called anywhere in the pipeline.
2. Nothing is stored: no column, table or JSONB field for correspondents exists.
3. The function has problems that must be fixed before wiring it in (see "Problems in the existing
   code").

Existing function, for reference:

```python
def tika_extract_correspondents(file_content: bytes):
    def ensure_list(value):
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            return value.split(";") if value else []
        return []

    try:
        parsed = parser.from_buffer(
            file_content,
            serverEndpoint=f"{settings.tika_url}/",
            requestOptions={'timeout': 300},
        )
        metadata = parsed.get('metadata', {})

        sender_email = ensure_list(metadata.get('Message:From-Email', ''))
        sender_name = ensure_list(metadata.get('Message:From-Name', ''))
        recipient_email = ensure_list(metadata.get('Message:To-Email', ''))
        recipient_name = ensure_list(metadata.get('Message-To', ''))
        cc_name = ensure_list(metadata.get('Message-Cc', ''))

        return sender_email, sender_name, recipient_email, recipient_name, cc_name
    except Exception as e:
        _logger.error(f"Tika extraction error: {e}")
        return "None"
```

## Problems in the existing code

1. **Mixed key families.** Sender and recipient emails use the `Message:...` property family
   (`Message:From-Email`, `Message:To-Email`), but recipient names and CC names use `Message-To` /
   `Message-Cc`, which are separate header-style constants. Tika's documented property family has Name
   and Email (plus Display-Name for recipients) for From, To, CC and BCC, so the CC email and all of
   BCC were simply never read. Use one consistent family.
2. **Failure returns the string `"None"`** instead of an empty result. A caller that unpacks a tuple
   raises `ValueError`. `TIKA_text_extract` has the same problem on its exception path. Return an empty
   result (no correspondents) instead, and fix `TIKA_text_extract` while touching this code.
3. **A second Tika parse.** The function re-parses the file with Tika. Called for every file, that
   doubles the Tika time. The first parse in `TIKA_text_extract` already has the metadata dict. Reuse
   it, and only look for correspondents when the mime type is an email type (for example
   `message/rfc822` for `.eml` and `application/vnd.ms-outlook` for `.msg`; confirm the exact list from
   real data).
4. **`ensure_list` splits strings on `;`.** Unverified guess. Names and addresses can contain
   separators. Tika returns multi-valued keys as lists; treat a single string as one value unless the
   real dump shows otherwise.

## Implementation without prior key verification (decided)

No real email files were available to dump Tika's metadata, so the exact key strings and value shapes
are unverified. Implement without that step, and build the extraction defensively so that correcting
it later is a small edit, not a rewrite:

- **One constants block for the keys.** Put every Tika key name in one place at the top of the module,
  so fixing a wrong key later is a one-line change.
- **Candidate keys per field.** For each value (sender, To, CC, BCC; name and email), try the
  documented `Message:<Role>-Email` / `Message:<Role>-Name` property keys first, then the header-style
  `Message-From` / `Message-To` / `Message-Cc` / `Message-Bcc`, and use the first non-empty value.
- **Prefer raw header strings when present.** If a header value looks like `Name <email>`, parse it
  with Python's `email.utils.getaddresses` to get correctly paired (name, email) tuples. Use the
  separate Name/Email properties as the fallback.
- **Accept lists and strings.** Tika returns multi-valued keys as lists. Treat a single string as one
  value; never split it on `;` or `,`, because display names can contain those characters.
- **Make wrong assumptions visible.** When a file has an email mime type but yields zero
  correspondents, log a warning with the file id and the list of `Message*` keys Tika did return. Log
  the raw values at debug level. A wrong key must show up in the logs, not as silently empty data.
- **Never block ingestion.** If correspondent extraction fails for a file, log it and continue with no
  rows for that file.

## Verify after implementation

Use the sample files in `sample-emails/` (`test-email-1-basic.eml`, `test-email-2-no-display-names.eml`,
`test-email-3-special-names.eml`): ingest them as an archive and check the stored rows.

- Email 1: one `from` row, two `to`, one `cc`, names and emails correctly paired. A `bcc` row only
  appears if Tika exposes the Bcc header; received mail normally has none, so its absence is not a bug.
- Email 2: addresses with empty names; nothing lost, nothing paired with the wrong person.
- Email 3: `Vermaercke, Karl` stays one name; `Peeters; An` stays one name; accents intact.
- `.msg`: unverified until a real file is available. Treat as best effort.

If the results are wrong, dump the raw Tika metadata for the failing file (the `Message*` keys are
already in the warning log) and correct the constants block.

## Value quality (from Tika's own documentation)

Tika documents that for Outlook (`.msg`) messages the "email" field can contain a name, the "name"
field can contain an email address, and values can be Exchange-style X500 addresses
(`/o=ExchangeLabs/ou=.../cn=Recipients/cn=...`). So:

- Do not assume the email field holds an email address. Validate with a simple email pattern.
- A value that fails validation is not stored as `email`. If it looks like a name, store it as `name`.
  X500 values are stored as `name` only, or skipped. Decide when seeing real data.
- Pairing names with emails by list position is only safe when both lists have the same length. If
  the raw header strings (`Message-From`, `Message-To`, `Message-Cc`, `Message-Bcc`) are present in the
  dump in `Name <email>` form, parsing them with Python's `email.utils.getaddresses` gives correctly
  paired (name, email) tuples without index pairing. Evaluate this against the real dump; use the
  Name/Email properties as the fallback where raw headers are absent (likely for `.msg`).

## Storage: separate table (decided)

```sql
CREATE TABLE file_correspondents (
    id UUID PRIMARY KEY,
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    archive_id UUID NOT NULL,
    role VARCHAR(10) NOT NULL,          -- 'from' | 'to' | 'cc' | 'bcc'
    email VARCHAR(320),
    name VARCHAR(500),
    position INTEGER NOT NULL DEFAULT 0, -- order within its role
    CHECK (email IS NOT NULL OR name IS NOT NULL)
);
CREATE INDEX idx_file_correspondents_file ON file_correspondents (file_id);
CREATE INDEX idx_file_correspondents_archive_email ON file_correspondents (archive_id, lower(email));
```

- One row per correspondent. The sender is a single row with role `from`; recipients are rows with
  role `to`, `cc` or `bcc`.
- `archive_id` is denormalized onto the table, the same pattern as `file_entities` / `file_topics`:
  archive-scoped queries need no join through `files`.
- Cascade: `file_id` references `files(id)` with `ON DELETE CASCADE`. Deleting an archive already
  cascades through its files, so correspondents are removed with it. Tika analysis has no redo flow, so
  no analysis-id chain is needed. If Tika re-extraction is ever added, it must delete that file's
  correspondents first.

## Write path

At ingestion, in the same place and transaction where the file's `tika_analyses` row is written: if
the mime type is an email type, extract the correspondents from the already-parsed metadata and insert
the rows in one bulk insert. Non-email files write nothing.

## Display (data side only)

The correspondents are shown in the file overview and hidden when a file has none, which is the case
for most files. The backend needs to expose them per file. If the overview already loads from an
existing per-file detail endpoint, add the correspondents there; otherwise add a small per-file
endpoint. Check which applies before deciding. UI design is covered separately.

## Backfill (open decision)

Archives ingested before this feature have no correspondent rows. Raw Tika metadata is not stored, and
the backend cannot read the original files (the agent can), so a backfill means re-reading the email
files through the agent. Either accept the gap (re-ingest an archive to get correspondents) or build a
backfill. Not decided.

## Testing

Sample files covering: an `.eml` with several To and CC recipients; a `.msg` (check for Exchange-style
addresses); a mail where recipients have no display names; a non-email file (no rows); non-ASCII names.

## Out of scope

- Searching or filtering by correspondent, and aggregates or charts (the flat table makes these easy
  later).
- UI design.
- Attachments of an email (Tika reports them as separate embedded documents; only the top-level
  message's correspondents are extracted).
- Mailbox files holding many messages.

## Open questions

- The exact key strings and value shapes: to be confirmed after implementation, using the sample
  files and the warning log described above.
- Whether to store X500 / unparseable values at all.
- Which endpoint feeds the file overview.
- Backfill for existing archives.