import json
import uuid


def _build_node(row: dict) -> dict:
    summary_analysis_ran = row["summary_model"] is not None
    ner_analysis_ran = row["ner_model"] is not None
    topics_analysis_ran = row["topics_model"] is not None

    return {
        "file_id": str(row["file_id"]),
        "relative_path": row["relative_path"],
        "name": row["name"],
        "is_directory": row["is_directory"],
        "extension": row["extension"],
        "size_bytes": row["size_bytes"],
        "mime_type": row["mime_type"],
        "language": row["language"],
        "word_count": row["word_count"],
        "author": row["author"],
        "content_excerpt": row["content_excerpt"],
        "generic_type": row["generic_type"],
        # summary/ner/topics are always present; null only if that analysis type was never run
        "summary": {
            "result": row["summary_result"],
            "model": row["summary_model"],
            "analyzed_at": row["summary_analyzed_at"],
        } if summary_analysis_ran else None,
        "ner": {
            "persons": row["ner_persons"],
            "locations": row["ner_locations"],
            "organisations": row["ner_organisations"],
            "misc": row["ner_misc"],
            "model": row["ner_model"],
            "analyzed_at": row["ner_analyzed_at"],
        } if ner_analysis_ran else None,
        "topics": {
            "topics": row["topics"],
            "model": row["topics_model"],
            "analyzed_at": row["topics_analyzed_at"],
        } if topics_analysis_ran else None,
        "children": [],
    }


def build_export_json(archive_header: dict, rows: list[dict]) -> str:
    # Build flat map of file_id → node
    nodes: dict[uuid.UUID, dict] = {}
    for row in rows:
        nodes[row["file_id"]] = _build_node(row)

    # Link children to parents; collect roots (parent_id is None)
    roots = []
    for row in rows:
        node = nodes[row["file_id"]]
        if row["parent_id"] is None:
            roots.append(node)
        else:
            parent = nodes.get(row["parent_id"])
            if parent is not None:
                parent["children"].append(node)

    return json.dumps(
        {"archive": archive_header, "tree": roots},
        ensure_ascii=False,
        indent=2,
        default=str,
    )
