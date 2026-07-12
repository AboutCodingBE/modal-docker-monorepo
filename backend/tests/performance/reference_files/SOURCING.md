# Bronkeuze voor text_source/*.jsonl: Wikipedia NL via Wikidata SPARQL + MediaWiki extracts

Representatief voor archiefdomeinen (Letterenhuis, ADVN, Amsab, Meemoo) en
gebalanceerd over de 4 NER-buckets uit `ner_engine.py` (`persons`,
`organisations`, `locations`, `misc`).

## Ophaalmethode

Geïmplementeerd in `fetch_wiki_source.py`. Elke categorie kiest 1 van deze
2 bronnen voor haar titellijst:

1. **Wikidata SPARQL** (`query.wikidata.org/sparql`) voor de entiteitenlijst
   van de meeste categorieën — filtert precies op klasse/eigenschap (bv.
   beroep=schrijver, nationaliteit=België) in plaats van te vertrouwen op
   Wikipedia-categorieën.
2. **Wikipedia-categorie-crawl** (MediaWiki `list=categorymembers`, geen
   Wikidata) voor onderwerpen waar Wikidata's eigen structuur te weinig
   oplevert — bv. de Vlaamse Beweging/ADVN-categorieën: Wikidata's `P135`
   ("movement") gaf maar 4 resultaten, terwijl Wikipedia's eigen categorieën
   (`Persoon`/`Organisatie`/`Tijdschrift binnen de Vlaamse Beweging`) veel
   rijker gecureerd bleken.
3. **MediaWiki** `action=query&prop=extracts&explaintext=1`
   (nl.wikipedia.org) voor de platte artikeltekst per titel, ongeacht welke
   van de twee bronnen hierboven de titel leverde. Let op: deze API staat
   max. **1 volledig artikel per request** toe (`exlimit` wordt door de
   TextExtracts-extensie automatisch teruggebracht naar 1 bij een niet-intro
   extract) — dus geen batching, wel rate-limiten tussen requests.
4. Licentie is **CC BY-SA**: attributie (URL per gebruikt artikel) staat
   samen met de tekst in hetzelfde record — geen apart attributiebestand
   dat uit sync kan raken.

## Output: 1 JSONL-bestand per categorie

Elke categorie in `CATEGORIES` (in `fetch_wiki_source.py`) heeft een korte
`slug` (bv. `vakbonden`, `advn_personen`) en wordt weggeschreven naar
`text_source/<slug>.jsonl`. Elke regel is 1 zelfstandig JSON-record:

```json
{"id": "ACV Puls", "url": "https://nl.wikipedia.org/wiki/ACV_Puls", "bucket": "organisations", "category": "vakbonden (BE)", "text": "..."}
```

Aparte bestanden per categorie (i.p.v. 1 groot gecombineerd bestand) maakt
het makkelijker om gericht te samplen — bv. enkel uit `gemeenten.jsonl`
putten, of een categorie later te vernieuwen zonder de rest opnieuw op te
halen.

Het totale corpus (som van alle `*.jsonl`-bestanden) hoeft niet zo groot te
zijn als het grootste testbestand (100MB) — `generator.py` moet straks alle
`*.jsonl`-bestanden inlezen, de `"text"`-velden samenvoegen tot 1 tekstpool,
en die met variatie hergebruiken/reshuffelen om bestanden van elke gevraagde
grootte te bouwen (zie NOTE.md in `text_source/` voor de bijgewerkte prompt).

## Categorieën, getest (2026-07-12)

| Bucket | Categorie | Bron | Artikelen |
|---|---|---|---|
| persons | Belgische schrijvers (P106=schrijver, P27=België) | SPARQL | 1620 |
| persons | Persoon binnen de Vlaamse Beweging (ADVN) | categorie | 200 |
| organisations | politieke partijen (P31=politieke partij, P17=België) | SPARQL | 174 |
| organisations | vakbonden (P31/P279*=vakbond, P17=België) | SPARQL | 74 |
| organisations | Organisatie binnen de Vlaamse Beweging (ADVN) | categorie | 96 |
| locations | gemeenten in België (P31=gemeente van België) | SPARQL | 585 |
| misc | literaire werken + toneelstukken (P407=Nederlands) | SPARQL | 1169 |
| misc | Tijdschrift binnen de Vlaamse Beweging (ADVN) | categorie | 15 |
| **totaal** | | | **3933** |

Geschat op basis van het gemeten gemiddelde uit een steekproef van 150
schrijver-artikelen (~4.0 KB/artikel, nog niet bevestigd voor de andere
categorieën): 3933 artikelen × ~4KB ≈ **15.4 MB** — ruim boven het beoogde
budget van ~8-10MB, dus deze categorieën volstaan zonder verder te moeten
uitbreiden.

Titels kunnen in meerdere categorieën van dezelfde bucket voorkomen (bv. een
organisatie die zowel "politieke partij" als "ADVN" is — zie de dubbele
"Algemeen Nederlands Arbeidersverbond" in de telling hierboven). Sinds elke
categorie haar eigen `*.jsonl`-bestand krijgt, wordt dit **niet**
gededupliceerd over categorieën heen: zo'n titel komt dan gewoon in beide
bestanden voor, elk met haar eigen `"category"`-label. Dat is bedoeld — elk
categoriebestand blijft zo zelfstandig/compleet voor wie enkel uit die ene
categorie wil samplen.

## Budget: entiteiten, niet KB

`--max-entities-per-bucket` (default 500) is de primaire maatstaf, niet KB.
Een KB-budget alleen kan door een paar toevallig lange artikelen
opgesoupeerd worden (bv. het ABVV-artikel is alleen al ~40KB) -- dat geeft
weinig entiteit-diversiteit, terwijl juist brede dekking van verschillende
entiteiten per NER-bucket het doel is. Het bucket-budget wordt gelijk
verdeeld over de categorieën erin, bv. bij default 500 en 3
organisations-categorieën: 500 // 3 = 166 artikelen elk.

`--max-kb-per-category` (optioneel, geen default) is een extra
veiligheidscap: laat een categorie vroeger stoppen als ze toevallig uit
ongewoon lange artikelen bestaat, ook al is het entiteiten-aandeel nog niet
gehaald.

`--all-entities` negeert `--max-entities-per-bucket` volledig en haalt élke
gevonden titel op (alle 3933) -- voor de volledige dataset in 1 keer.
Combineer eventueel met `--max-kb-per-category` als je toch een
veiligheidscap wil tegen uitzonderlijk lange artikelen.

## Hoe uitvoeren

```bash
cd tests/performance/reference_files

# stap 1: enkel titels ophalen en tellen, geen tekst downloaden (snel, ~seconden)
python fetch_wiki_source.py --titles-only

# kleine testrun: klein entiteiten-budget, naar een tijdelijke map
python fetch_wiki_source.py --max-entities-per-bucket 8 --output-dir /tmp/sample_test

# volledige run: schrijft de echte tests/performance/reference_files/text_source/<slug>.jsonl
# per categorie. Duurt ~10-15 minuten (1 HTTP-request per artikel, rate-limited).
python fetch_wiki_source.py --max-entities-per-bucket 500

# met optionele KB-veiligheidscap per categorie
python fetch_wiki_source.py --max-entities-per-bucket 500 --max-kb-per-category 800

# volledige dataset: ALLE gevonden artikelen (3933), geen cap
python fetch_wiki_source.py --all-entities
```

`--output-dir` default is `text_source/` naast dit script.
