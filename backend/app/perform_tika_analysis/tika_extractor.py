import os

from app.config import settings

# Tell the tika Python client to use our remote server, not spin up a local JVM.
os.environ['TIKA_CLIENT_ONLY'] = 'True'
os.environ['TIKA_SERVER_ENDPOINT'] = settings.tika_url

from tika import parser, language, detector


def TIKA_text_extract(file_content: bytes):
    """
    Extracts text and metadata from file content bytes using Apache Tika.

    Returns a tuple of (mime_type, text, tika_parser, text_language, creation_date, creator),
    or the string "None" if extraction fails.
    """
    try:
        parsed = parser.from_buffer(
            file_content,
            serverEndpoint=f"{settings.tika_url}/",
            requestOptions={'timeout': 300},
        )

        text = parsed.get('content', '')
        metadata = parsed.get('metadata', {})

        text_language = language.from_buffer(text)
        file_mimetype = detector.from_buffer(file_content)

        creation_date = metadata.get('dcterms:created') or None
        creator = metadata.get('dc:creator', '')
        tika_parser = metadata.get('X-TIKA:Parsed-By-Full-Set', 'Unknown')

        return file_mimetype, text, tika_parser, text_language, creation_date, creator
    except Exception as e:
        print(f"An error occurred: {e}")
        return "None"


def tika_extract_correspondents(file_content: bytes):
    """
    Extracts email correspondent metadata from file content bytes using Apache Tika.

    Returns a tuple of (sender_email, sender_name, recipient_email, recipient_name, cc_name),
    or the string "None" if extraction fails.
    """
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
        print(f"An error occurred: {e}")
        return "None"
