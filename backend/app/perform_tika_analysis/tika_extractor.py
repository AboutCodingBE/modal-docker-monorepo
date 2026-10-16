import logging
import os
import re
from email import utils as email_utils

from app.config import settings

_logger = logging.getLogger("app.tika")

# Tell the tika Python client to use our remote server, not spin up a local JVM.
os.environ['TIKA_CLIENT_ONLY'] = 'True'
os.environ['TIKA_SERVER_ENDPOINT'] = settings.tika_url

from tika import parser, language, detector

# ---------------------------------------------------------------------------
# Email MIME types that may carry correspondent metadata
# ---------------------------------------------------------------------------
EMAIL_MIME_TYPES = {"message/rfc822", "application/vnd.ms-outlook"}

# ---------------------------------------------------------------------------
# Tika metadata key constants for email correspondent fields.
# Each entry is a list of candidate keys tried in order; the first non-empty
# value wins.  Fixing a wrong key later is a one-line change here.
# ---------------------------------------------------------------------------
_TIKA_KEYS = {
    "from_raw":   ["Message:From",     "Message-From"],
    "from_email": ["Message:From-Email"],
    "from_name":  ["Message:From-Name"],
    "to_raw":     ["Message:To",       "Message-To"],
    "to_email":   ["Message:To-Email"],
    "to_name":    ["Message:To-Name"],
    "cc_raw":     ["Message:Cc",       "Message-Cc"],
    "cc_email":   ["Message:Cc-Email"],
    "cc_name":    ["Message:Cc-Name"],
    "bcc_raw":    ["Message:Bcc",      "Message-Bcc"],
    "bcc_email":  ["Message:Bcc-Email"],
    "bcc_name":   ["Message:Bcc-Name"],
}

# Simple email validator — avoids assuming Tika's "email" field holds an address.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def TIKA_text_extract(
    file_content: bytes,
    ocr_enabled: bool = False,
    ocr_language: str | None = None,
):
    """
    Extracts text and metadata from file content bytes using Apache Tika.

    Returns a tuple of (mime_type, text, tika_parser, text_language,
    creation_date, creator, metadata), or None if extraction fails.

    ocr_language: Tesseract language string (e.g. 'nld+eng') sent as
    X-Tika-OCRLanguage. Only used when ocr_enabled is True.
    """
    try:
        headers = {} if ocr_enabled else {'X-Tika-OCRskipOcr': 'true'}
        if ocr_enabled and ocr_language:
            headers['X-Tika-OCRLanguage'] = ocr_language
        parsed = parser.from_buffer(
            file_content,
            serverEndpoint=settings.tika_url,
            requestOptions={'timeout': 300, 'headers': headers},
        )

        raw_content = parsed.get('content')
        text = raw_content if raw_content is not None else ''
        metadata = parsed.get('metadata', {})
        _logger.debug(
            f"Tika parsed result: status={parsed.get('status')}, "
            f"content_length={len(text)}, metadata_keys={list(metadata.keys())}"
        )

        text_language = language.from_buffer(text)
        file_mimetype = detector.from_buffer(file_content)

        creation_date = metadata.get('dcterms:created') or None
        creator = metadata.get('dc:creator', '')
        tika_parser = metadata.get('X-TIKA:Parsed-By-Full-Set', 'Unknown')

        return file_mimetype, text, tika_parser, text_language, creation_date, creator, metadata
    except Exception as e:
        _logger.error(f"Tika extraction error: {e}")
        return None


# ---------------------------------------------------------------------------
# Correspondent extraction helpers
# ---------------------------------------------------------------------------

def _get_values(metadata: dict, keys: list[str]) -> list[str]:
    """Return the first non-empty value from metadata for the given candidate
    keys, as a list of strings.  A single string is returned as a one-element
    list; never split on separators."""
    for key in keys:
        val = metadata.get(key)
        if val is None or val == '':
            continue
        if isinstance(val, list):
            result = [str(v) for v in val if v]
            if result:
                return result
        else:
            return [str(val)]
    return []


def _validate_email(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    return v if _EMAIL_RE.match(v) else None


def _extract_role_pairs(
    metadata: dict,
    raw_keys: list[str],
    email_keys: list[str],
    name_keys: list[str],
) -> list[tuple[str | None, str | None]]:
    """Return a list of (name, email) pairs for one role.

    Preferred path: parse raw header strings with email.utils.getaddresses so
    that quoted names like "Vermaercke, Karl" are kept intact.
    Fallback: separate Name/Email property lists, paired by position.
    """
    raw_values = _get_values(metadata, raw_keys)
    if raw_values:
        _logger.debug(f"Parsing raw header values: {raw_values}")
        pairs = email_utils.getaddresses(raw_values)
        return [(name.strip() or None, addr.strip() or None) for name, addr in pairs]

    emails = _get_values(metadata, email_keys)
    names = _get_values(metadata, name_keys)
    max_len = max(len(emails), len(names), 0)
    result = []
    for i in range(max_len):
        e = emails[i] if i < len(emails) else None
        n = names[i] if i < len(names) else None
        result.append((n or None, e or None))
    return result


def extract_correspondents_from_metadata(metadata: dict, file_id: str) -> list[dict]:
    """Extract correspondent rows from an already-parsed Tika metadata dict.

    Returns a list of dicts with keys: role, email, name, position.
    Never raises; returns an empty list on any error.
    """
    try:
        correspondents: list[dict] = []

        role_configs = [
            (
                "from",
                _TIKA_KEYS["from_raw"],
                _TIKA_KEYS["from_email"],
                _TIKA_KEYS["from_name"],
            ),
            (
                "to",
                _TIKA_KEYS["to_raw"],
                _TIKA_KEYS["to_email"],
                _TIKA_KEYS["to_name"],
            ),
            (
                "cc",
                _TIKA_KEYS["cc_raw"],
                _TIKA_KEYS["cc_email"],
                _TIKA_KEYS["cc_name"],
            ),
            (
                "bcc",
                _TIKA_KEYS["bcc_raw"],
                _TIKA_KEYS["bcc_email"],
                _TIKA_KEYS["bcc_name"],
            ),
        ]

        for role, raw_keys, email_keys, name_keys in role_configs:
            pairs = _extract_role_pairs(metadata, raw_keys, email_keys, name_keys)
            for position, (name, email_raw) in enumerate(pairs):
                email = _validate_email(email_raw)

                # If email_raw fails validation, treat it as a name when no
                # name is present (handles X500 / Exchange-style values).
                if email is None and email_raw and not name:
                    name = email_raw

                if email is None and name is None:
                    continue

                correspondents.append({
                    "role": role,
                    "email": email,
                    "name": name,
                    "position": position,
                })

        if not correspondents:
            msg_keys = [k for k in metadata if k.startswith("Message")]
            _logger.warning(
                f"Email file {file_id} has email MIME type but zero correspondents extracted. "
                f"Message* keys present: {msg_keys}"
            )
        else:
            _logger.debug(f"Extracted {len(correspondents)} correspondents for file {file_id}")

        return correspondents

    except Exception as e:
        _logger.error(f"Correspondent extraction failed for file {file_id}: {e}")
        return []
