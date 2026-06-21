"""Genereert testfixtures voor de integratietests.

Uitvoeren vanuit de backend-map:
    python tests/testdata/create_testdata.py

Gegenereerde bestanden worden mee gecommit zodat tests reproduceerbaar zijn
zonder runtime-generatie. Draai dit script opnieuw als je een fixture aanpast.
"""

import sys
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
