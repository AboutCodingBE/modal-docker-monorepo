import csv
import io

_COLUMNS = [
    "relative_path", "name", "is_directory", "extension", "size_bytes",
    "mime_type", "language", "word_count", "author", "content_excerpt",
    "generic_type",
    "summary_result", "summary_model", "summary_analyzed_at",
    "ner_persons", "ner_locations", "ner_organisations", "ner_misc", "ner_model", "ner_analyzed_at",
    "topics", "topics_model", "topics_analyzed_at",
]


def _to_csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        # Semicolon delimiter avoids ambiguity with the CSV comma delimiter.
        # Known limitation: a semicolon inside an entity/topic name is indistinguishable
        # from two separate entries once joined — accepted, documented in context.md.
        return ";".join(str(v) for v in value)
    return str(value)


def build_export_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_COLUMNS)
    for row in rows:
        writer.writerow([_to_csv_cell(row.get(col)) for col in _COLUMNS])
    return output.getvalue()
