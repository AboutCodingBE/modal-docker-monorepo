"""Eenmalig hulpscript dat tests/performance/reference_files/text_source/*.jsonl
opbouwt uit Nederlandstalige Wikipedia-artikelen, gebalanceerd over de 4
NER-buckets (persons, organisations, locations, misc) uit
backend/app/create_ner_for_archive/ner_engine.py.

Schrijft 1 JSONL-bestand per categorie (bestandsnaam = de "slug" in
CATEGORIES hieronder), met per regel:
{"id": <titel>, "url": ..., "bucket": ..., "category": <label>, "text": ...}
-- zo blijven tekst en attributie (CC BY-SA) samen in 1 bestand per categorie,
en is makkelijk per categorie te samplen zonder alles te moeten inlezen.

Methode: Wikidata SPARQL voor de entiteitenlijst per categorie, dan de
MediaWiki extracts-API voor de platte artikeltekst per titel. Zie
SOURCING.md voor de achtergrond en de geteste categorie-aantallen.

Dit is geen onderdeel van de pytest-suite (geen test_-bestand) en wordt niet
automatisch gedraaid — enkel handmatig, om het bronbestand op te bouwen of te
vernieuwen.

Vereisten om te draaien: internettoegang (query.wikidata.org,
nl.wikipedia.org). Geen DB/Tika/Ollama nodig.
"""

import argparse
import sys
import time
import urllib.parse
import urllib.request
import json
from pathlib import Path

USER_AGENT = "ModalUnitBenchmarkTest/0.1 (research; contact: drdwitte@gmail.com)"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
MEDIAWIKI_API = "https://nl.wikipedia.org/w/api.php"

# Bucket -> lijst van categorie-definities. Twee bronnen:
# - {"source": "sparql", "query": ...}     Wikidata SPARQL, precieze klasse/eigenschap-filters.
# - {"source": "category", "category": ...} Wikipedia-categorie (MediaWiki), voor onderwerpen
#   waar Wikidata's eigen structuur (P135 "movement" ea.) te weinig oplevert, bv. Vlaamse
#   Beweging/ADVN -- Wikipedia's categorieboom is daar veel rijker gecureerd.
# Zie SOURCING.md voor de geteste aantallen per categorie (stand 2026-07-12).
CATEGORIES: dict[str, list[dict]] = {
    "persons": [
        {
            "label": "Belgische schrijvers",
            "slug": "schrijvers",
            "source": "sparql",
            "query": """
                SELECT DISTINCT ?article WHERE {
                  ?person wdt:P106 wd:Q36180 .
                  ?person wdt:P27 wd:Q31 .
                  ?article schema:about ?person ; schema:isPartOf <https://nl.wikipedia.org/> .
                }
            """,
        },
        {
            "label": "Persoon binnen de Vlaamse Beweging (ADVN)",
            "slug": "advn_personen",
            "source": "category",
            "category": "Persoon binnen de Vlaamse Beweging",
        },
    ],
    "organisations": [
        {
            "label": "politieke partijen (BE)",
            "slug": "politieke_partijen",
            "source": "sparql",
            "query": """
                SELECT DISTINCT ?article WHERE {
                  ?org wdt:P31 wd:Q7278 .
                  ?org wdt:P17 wd:Q31 .
                  ?article schema:about ?org ; schema:isPartOf <https://nl.wikipedia.org/> .
                }
            """,
        },
        {
            "label": "vakbonden (BE)",
            "slug": "vakbonden",
            "source": "sparql",
            "query": """
                SELECT DISTINCT ?article WHERE {
                  ?org wdt:P31/wdt:P279* wd:Q178790 .
                  ?org wdt:P17 wd:Q31 .
                  ?article schema:about ?org ; schema:isPartOf <https://nl.wikipedia.org/> .
                }
            """,
        },
        {
            "label": "Organisatie binnen de Vlaamse Beweging (ADVN)",
            "slug": "advn_organisaties",
            "source": "category",
            "category": "Organisatie binnen de Vlaamse Beweging",
        },
    ],
    "locations": [
        {
            "label": "gemeenten in Belgie",
            "slug": "gemeenten",
            "source": "sparql",
            "query": """
                SELECT DISTINCT ?article WHERE {
                  ?loc wdt:P31 wd:Q493522 .
                  ?article schema:about ?loc ; schema:isPartOf <https://nl.wikipedia.org/> .
                }
            """,
        },
    ],
    "misc": [
        {
            "label": "literaire werken + toneelstukken (NL-taal)",
            "slug": "literaire_werken",
            "source": "sparql",
            "query": """
                SELECT DISTINCT ?article WHERE {
                  ?work wdt:P31/wdt:P279* ?type .
                  VALUES ?type { wd:Q7725634 wd:Q25379 }
                  ?work wdt:P407 wd:Q7411 .
                  ?article schema:about ?work ; schema:isPartOf <https://nl.wikipedia.org/> .
                }
                LIMIT 5000
            """,
        },
        {
            "label": "Tijdschrift binnen de Vlaamse Beweging (ADVN)",
            "slug": "advn_tijdschriften",
            "source": "category",
            "category": "Tijdschrift binnen de Vlaamse Beweging",
        },
    ],
}


def sparql_titles(query: str) -> list[str]:
    """Voert een SPARQL-query uit tegen Wikidata en geeft de nl.wikipedia-artikeltitels terug."""
    url = SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    titles = []
    for row in data["results"]["bindings"]:
        article_url = row["article"]["value"]
        title = urllib.parse.unquote(article_url.rsplit("/", 1)[-1]).replace("_", " ")
        titles.append(title)
    return sorted(set(titles))


def wikipedia_category_titles(category: str) -> list[str]:
    """Geeft de titels van alle artikelen (niet: subcategorieen) direct in een nl.wikipedia-categorie.

    Gebruikt geen SPARQL/Wikidata: rechtstreeks de MediaWiki-API van
    nl.wikipedia.org zelf (categorymembers), dus volgt hoe Wikipedia-redacteurs
    artikelen effectief in categorieen hebben ingedeeld, i.p.v. gestructureerde
    Wikidata-feiten (beroep, nationaliteit, ...). Voor de meeste buckets werkt
    sparql_titles() goed genoeg; voor de ADVN/Vlaamse Beweging-categorieen gaf
    Wikidata's P135 ("movement") maar 4 resultaten terwijl Wikipedia's eigen
    categorieboom (Categorie:Persoon/Organisatie/Tijdschrift binnen de Vlaamse
    Beweging) veel rijker gecureerd bleek.
    """
    titles = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Categorie:{category}",
            "cmlimit": 500,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        url = MEDIAWIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members if m["ns"] == 0)
        if "continue" in data:
            cmcontinue = data["continue"]["cmcontinue"]
        else:
            break
    return sorted(set(titles))


def fetch_extract(title: str) -> str:
    """Haalt de platte tekst-extract van 1 nl.wikipedia-artikel op.

    De TextExtracts-API staat max. 1 volledig (niet-intro) artikel per
    request toe (exlimit wordt anders automatisch teruggebracht naar 1) --
    dus geen batching, wel 1 request per titel.
    """
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "format": "json",
        "titles": title,
    }
    url = MEDIAWIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        return page.get("extract", "")
    return ""


def build_category_datasets(
    all_titles: dict[str, list[dict]],
    max_entities_per_bucket: int | None,
    output_dir: Path,
    max_kb_per_category: float | None = None,
    sleep_sec: float = 0.15,
) -> None:
    """Haalt per categorie extracts op tot het aandeel van het
    bucket-entiteitenbudget gehaald is, en schrijft 1 JSONL-bestand per
    categorie naar output_dir (bestandsnaam = de "slug", bv.
    text_source/vakbonden.jsonl). Elke regel: {"id", "url", "bucket",
    "category", "text"} -- tekst en CC BY-SA-attributie blijven zo samen in
    1 bestand per categorie.

    Entiteitenaantal (niet KB) is de primaire maatstaf: een KB-budget alleen
    kan door een paar uitzonderlijk lange artikelen opgesoupeerd worden (bv.
    het ABVV-artikel was alleen al ~40KB), wat weinig entiteit-diversiteit
    oplevert -- terwijl we net brede dekking van verschillende entiteiten
    per NER-bucket willen. max_kb_per_category is een optionele
    veiligheidscap die een categorie vroeger laat stoppen als ze toevallig
    uit ongewoon lange artikelen bestaat.

    max_entities_per_bucket=None betekent geen cap: elke categorie haalt dan
    alle gevonden titels op (--all-entities in de CLI).

    Het bucket-budget wordt gelijk verdeeld over de categorieen binnen die
    bucket (geen round-robin/interleaving meer nodig nu elke categorie haar
    eigen bestand krijgt).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    max_kb_bytes = None if max_kb_per_category is None else int(max_kb_per_category * 1024)

    for bucket, definitions in all_titles.items():
        if not definitions:
            continue
        for definition in definitions:
            per_category_entities = (
                len(definition["titles"]) if max_entities_per_bucket is None
                else max_entities_per_bucket // len(definitions)
            )
            slug = definition["slug"]
            out_path = output_dir / f"{slug}.jsonl"
            written_bytes = 0
            fetched = 0
            with out_path.open("w", encoding="utf-8") as f:
                for title in definition["titles"]:
                    if fetched >= per_category_entities:
                        break
                    if max_kb_bytes is not None and written_bytes >= max_kb_bytes:
                        break
                    extract = fetch_extract(title)
                    time.sleep(sleep_sec)
                    if not extract:
                        continue
                    url = "https://nl.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
                    record = {
                        "id": title,
                        "url": url,
                        "bucket": bucket,
                        "category": definition["label"],
                        "text": extract,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_bytes += len(extract.encode("utf-8"))
                    fetched += 1
            print(f"[{bucket}/{slug}] {fetched} artikelen, {written_bytes/1024:.1f} KB -> {out_path}")


def fetch_all_titles() -> dict[str, list[dict]]:
    """Haalt voor elke bucket en categorie de artikeltitels op.

    Geeft {bucket: [{...CATEGORIES-definitie..., "titles": [...]}]} terug --
    elke categorie-definitie uit CATEGORIES aangevuld met haar opgehaalde titels.
    """
    result: dict[str, list[dict]] = {}
    for bucket, definitions in CATEGORIES.items():
        result[bucket] = []
        for definition in definitions:
            if definition["source"] == "sparql":
                titles = sparql_titles(definition["query"])
            elif definition["source"] == "category":
                titles = wikipedia_category_titles(definition["category"])
            else:
                raise ValueError(f"onbekende source: {definition['source']}")
            result[bucket].append({**definition, "titles": titles})
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--titles-only", action="store_true",
        help="Enkel titels ophalen en tellen (stap 1), geen tekst downloaden.",
    )
    parser.add_argument(
        "--max-entities-per-bucket", type=int, default=500,
        help="Max. aantal artikelen per NER-bucket, gelijk verdeeld over de "
             "categorieen erin (default 500). Primaire maatstaf i.p.v. KB, "
             "zodat entiteit-diversiteit niet opgesoupeerd wordt door een "
             "paar toevallig lange artikelen. Genegeerd als --all-entities is gezet.",
    )
    parser.add_argument(
        "--all-entities", action="store_true",
        help="Geen cap: haal ALLE gevonden titels per categorie op "
             "(negeert --max-entities-per-bucket). Voor de volledige dataset "
             "(3933 artikelen, ~10-15 min); overweeg --max-kb-per-category "
             "erbij als veiligheidscap tegen uitzonderlijk lange artikelen.",
    )
    parser.add_argument(
        "--max-kb-per-category", type=float, default=None,
        help="Optionele veiligheidscap (KB) per categorie: stopt vroeger "
             "als bereikt, ook al is het entiteiten-aandeel nog niet gehaald.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).parent / "text_source",
        help="Waar de <slug>.jsonl-bestanden per categorie geschreven worden.",
    )
    args = parser.parse_args()

    all_titles = fetch_all_titles()
    grand_total = 0
    for bucket, definitions in all_titles.items():
        bucket_total = sum(len(d["titles"]) for d in definitions)
        grand_total += bucket_total
        print(f"[{bucket}] totaal {bucket_total} artikelen")
        for d in definitions:
            print(f"  - {d['label']} ({d['slug']}): {len(d['titles'])} ({d['titles'][:3]}...)")
    print(f"\nGrand totaal: {grand_total} artikelen (uniek per categorie, kan overlap bevatten tussen categorieen)")

    if not args.titles_only:
        entities_cap = None if args.all_entities else args.max_entities_per_bucket
        print(
            "\nExtracts ophalen ("
            + ("alle gevonden artikelen" if entities_cap is None else f"max {entities_cap} artikelen per bucket, verdeeld over de categorieen erin")
            + (f", max {args.max_kb_per_category} KB per categorie" if args.max_kb_per_category else "")
            + ")..."
        )
        build_category_datasets(
            all_titles, entities_cap, args.output_dir,
            max_kb_per_category=args.max_kb_per_category,
        )
