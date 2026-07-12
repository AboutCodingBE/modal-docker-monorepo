# TODO — bronbestanden voor generator.py

Hier horen `<slug>.jsonl`-bestanden te komen (1 per categorie, bv.
`schrijvers.jsonl`, `vakbonden.jsonl`, `gemeenten.jsonl`, ... — zie
`fetch_wiki_source.py` voor de volledige lijst), geproduceerd door
`../fetch_wiki_source.py`. Elke regel is een JSON-record met échte,
betekenisvolle Nederlandse tekst (`"text"`-veld, geen lorem ipsum, geen
herhaalde/identieke content) + attributie (`"url"`).

`reference_files/generator.py` moet deze `*.jsonl`-bestanden inlezen (over
alle categorieën heen), de `"text"`-velden samenvoegen tot 1 tekstpool, en
die in stukken knippen/variëren om unieke testbestanden op exacte grootte te
genereren (tot en met 100MB, via hergebruik met variatie — de tekstpool zelf
hoeft niet zo groot te zijn als het grootste testbestand).

Wordt aangemaakt als onderdeel van sectie 1.1 in
`MODAL_performance_benchmarks.md` (zie de Claude Code-prompt in
`../generator.py`).

Voor de bronkeuze en ophaalmethode (Wikipedia NL via Wikidata SPARQL +
MediaWiki extracts, categorietabel, licentie), zie
[`../SOURCING.md`](../SOURCING.md).
