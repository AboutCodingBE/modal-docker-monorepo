"""Genereert testfixtures voor de integratietests.

Uitvoeren vanuit de backend-map:
    python tests/testdata/create_testdata.py

Gegenereerde bestanden worden mee gecommit zodat tests reproduceerbaar zijn
zonder runtime-generatie. Draai dit script opnieuw als je een fixture aanpast.
"""

import io
import sys
import zipfile
from pathlib import Path

# Windows-terminals gebruiken standaard cp1252; zet stdout op UTF-8 zodat
# bestandsnamen met unicode (Japans, Arabisch, emoji) correct geprint worden.
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def create_normaal_pdf() -> bytes:
    """Minimale geldige PDF met bekende Nederlandstalige tekst en /Author + /CreationDate metadata.

    De inhoud is bewust eenvoudig gehouden zodat de test deterministisch is.
    Tika extraheert hieruit:
    - mime_type: application/pdf
    - content: bevat 'testdocument', 'gemeentearchief', etc.
    - dc:creator: J. Janssen  (uit /Author)
    - dcterms:created: 2023-03-15T10:30:00Z  (uit /CreationDate)
    """
    stream_content = (
        b"BT\n"
        b"/F1 12 Tf\n"
        b"72 720 Td\n"
        b"(Dit is een testdocument van het gemeentearchief.) Tj\n"
        b"0 -20 Td\n"
        b"(Het bevat meerdere Nederlandse zinnen voor taaldetectie.) Tj\n"
        b"0 -20 Td\n"
        b"(Auteur: J. Janssen. Datum: vijftien maart tweeduizend drieentwintig.) Tj\n"
        b"ET"
    )

    obj1 = b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
    obj2 = b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
    obj3 = (
        b"3 0 obj\n"
        b"<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>>\n"
        b"endobj\n"
    )
    obj4 = (
        b"4 0 obj\n<</Length " + str(len(stream_content)).encode() + b">>\n"
        b"stream\n" + stream_content + b"\nendstream\nendobj\n"
    )
    obj5 = b"5 0 obj\n<</Type /Font /Subtype /Type1 /BaseFont /Helvetica>>\nendobj\n"
    obj6 = b"6 0 obj\n<</Author (J. Janssen) /CreationDate (D:20230315103000Z)>>\nendobj\n"

    header = b"%PDF-1.4\n"
    objects = [obj1, obj2, obj3, obj4, obj5, obj6]

    offsets = []
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        pos += len(obj)

    xref_offset = pos
    xref = b"xref\n0 7\n"
    xref += b"0000000000 65535 f \n"
    for offset in offsets:
        xref += (str(offset).zfill(10) + " 00000 n \n").encode()

    trailer = (
        b"trailer\n<</Size 7 /Root 1 0 R /Info 6 0 R>>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )

    return header + b"".join(objects) + xref + trailer


def create_corrupt_pdf() -> bytes:
    """PDF-header gevolgd door ongeldige inhoud.

    Tika herkent de %PDF-header en probeert het als PDF te parsen,
    maar de structuur is volledig ongeldig. Bedoeld om te testen of
    de pipeline niet crasht bij een corrupt bestand.
    """
    return b"%PDF-1.4\nCORRUPTE INHOUD - GEEN GELDIGE PDF-STRUCTUUR\xff\xfe\xfd"


def create_normaal_docx() -> bytes:
    """Minimale geldige DOCX met Nederlandstalige tekst en auteurmetadata.

    DOCX is een ZIP-bestand met XML-onderdelen. De minimale structuur bevat:
      - [Content_Types].xml  — welke onderdelen er in de ZIP zitten
      - _rels/.rels          — verwijzing naar het hoofddocument
      - word/document.xml    — de eigenlijke tekst
      - docProps/core.xml    — auteur en aanmaakdatum (dc:creator, dcterms:created)

    Tika extraheert hieruit:
      - mime_type : application/vnd.openxmlformats-officedocument.wordprocessingml.document
      - content   : bevat 'testdocument' en 'gemeentearchief'
      - dc:creator: T. Testpersoon
      - dcterms:created: 2007-01-15T09:00:00Z
    """
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml"'
        ' ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        '<Relationship Id="rId2"'
        ' Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"'
        ' Target="docProps/core.xml"/>'
        '</Relationships>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>Dit is een testdocument van het gemeentearchief in DOCX-formaat.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Het bevat meerdere Nederlandse zinnen voor taaldetectie.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Auteur: T. Testpersoon. Datum: vijftien januari tweeduizend zeven.</w:t></w:r></w:p>'
        '</w:body>'
        '</w:document>'
    )
    word_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties'
        ' xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:dcterms="http://purl.org/dc/terms/"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>T. Testpersoon</dc:creator>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">2007-01-15T09:00:00Z</dcterms:created>'
        '</cp:coreProperties>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", word_rels)
        zf.writestr("docProps/core.xml", core)
    return buf.getvalue()


# Bestandsnamen voor M1.01 — exotische bestandsnamen.
# Lege bestanden (0 bytes): de content is niet relevant, alleen de naam telt.
M1_EXOTIC_NAMES = [
    "café résumé été.pdf",
    "rapport (versie 2) & bijlage.docx",
    "Müller & Söhne GmbH.xlsx",
    "factuur [2024] #1.txt",
    "bestand met spaties in naam.pdf",
    "日本語ファイル.pdf",
    "ملف عربي.docx",
    "файл_на_русском.txt",
    "∑∆π formules.xlsx",
    "emoji 🎉 bestand.pdf",
]


def create_groot_bestand() -> bytes:
    """Herhalende Nederlandse tekst tot ~10MB voor grote-bestandstests.

    Tika extraheert hieruit:
      - mime_type: text/plain
      - content: lange tekst met 'gemeentearchief' en 'testdocument'
      - word_count: ruim boven 10.000
    """
    zin = (
        "Dit is een testdocument van het gemeentearchief met Nederlandse tekst "
        "voor de taaldetectie en verwerking van grote bestanden. "
    )
    doel_bytes = 10 * 1024 * 1024  # 10 MB
    herhalingen = doel_bytes // len(zin.encode("utf-8")) + 1
    return (zin * herhalingen).encode("utf-8")[:doel_bytes]


if __name__ == "__main__":
    root = Path(__file__).parent

    # data_M1 — lege bestanden met exotische namen
    data_m1 = root / "data_M1"
    data_m1.mkdir(parents=True, exist_ok=True)
    for name in M1_EXOTIC_NAMES:
        (data_m1 / name).touch()
        print(f"Aangemaakt: data_M1/{name}")

    # data_M2 — PDF met tekst en metadata voor Tika-tests
    data_m2 = root / "data_M2"
    data_m2.mkdir(parents=True, exist_ok=True)
    pdf_path = data_m2 / "normaal_document.pdf"
    pdf_path.write_bytes(create_normaal_pdf())
    print(f"Aangemaakt: data_M2/{pdf_path.name}")

    corrupt_path = data_m2 / "corrupt_document.pdf"
    corrupt_path.write_bytes(create_corrupt_pdf())
    print(f"Aangemaakt: data_M2/{corrupt_path.name}")

    leeg_path = data_m2 / "leeg_bestand.txt"
    leeg_path.write_bytes(b"")
    print(f"Aangemaakt: data_M2/{leeg_path.name}")

    docx_path = data_m2 / "normaal_document.docx"
    docx_path.write_bytes(create_normaal_docx())
    print(f"Aangemaakt: data_M2/{docx_path.name}")

    groot_path = data_m2 / "groot_bestand.txt"
    groot_path.write_bytes(create_groot_bestand())
    print(f"Aangemaakt: data_M2/{groot_path.name} ({groot_path.stat().st_size // (1024*1024)}MB)")
