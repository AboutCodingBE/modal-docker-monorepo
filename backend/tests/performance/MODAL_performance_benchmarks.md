# MODAL — Performance Benchmark Suite

Doel: reproduceerbare, timestamped timing-metingen van ingest, analyses en queries op schalende testdata, weggeschreven als append-only log (JSONL) voor latere plotting en regressie-detectie.

Dit is **geen unit test suite** (correctheid) maar een **benchmark suite** (snelheid). Aparte map, aparte pytest-marker, niet in de normale CI-run.

---

## Waar komt dit te staan

```
tests/performance/
├── README.md                          # korte uitleg van deze suite
├── reference_files/
│   ├── generator.py                   # genereert unieke NL-tekstbestanden op exacte grootte
│   ├── text_source/                   # bron van representatieve NL-tekst (geen lorem ipsum)
│   └── generated/                     # output van generator.py — gitignored, on-demand gegenereerd
├── manifests/
│   └── *.json                         # testcombinaties (count × size)
├── fixtures/
│   ├── warmup.py                      # Ollama warm-up functie
│   ├── assembler.py                   # manifest → tijdelijke ingest-folder
│   └── logger.py                      # timing decorator + JSONL-writer
├── logs/
│   └── benchmarks.jsonl               # append-only resultatenlog — WEL committen (historiek!)
├── scaling/
│   ├── test_ingest_scaling_size.py
│   ├── test_ingest_scaling_count.py
│   ├── test_ingest_scaling_combined.py
│   ├── test_ocr_overhead.py
│   ├── test_ner_scaling.py
│   └── test_summary_scaling.py
├── queries/
│   ├── test_fulltext_search_scaling.py
│   └── test_vector_search_scaling.py
├── realistic/
│   ├── archive_stats.py               # analyseert een écht archief (bv. VEA260)
│   └── test_realistic_snapshot.py     # sanity-check op vaste, gekopieerde échte data
└── analysis/
    └── plot_benchmarks.py             # leest benchmarks.jsonl in, plot + curve fit
```

**Belangrijk:** `benchmarks.jsonl` committen we wél naar git (in tegenstelling tot `generated/`), zodat de historiek van performance over commits heen bewaard blijft en teamleden dezelfde data zien.

Elke JSONL-regel bevat minstens: `timestamp, git_commit, manifest_id, phase, model_used, file_count, file_size_kb, total_corpus_kb, ocr_used, device, run_type (cold/warm), db_row_count, db_size_mb, duration_sec`.

Draai de suite apart met: `pytest tests/performance/ -m benchmark`

---

## 1. Setup & Harness

### 1.1 Reference file generator
**Wat we testen:** niets — dit is infrastructuur. Genereert unieke bestanden met representatieve NL-tekst (geen herhaalde/identieke content, geen betekenisloze tekst) op exacte, parametriseerbare groottes.

**Claude Code prompt:**
```
Maak tests/performance/reference_files/generator.py met een functie
generate_file(size_kb: int, index: int, filetype: str, output_dir: Path) -> Path
die een bestand genereert met representatieve Nederlandse tekst (gebruik een bronbestand
tests/performance/reference_files/text_source/sample_nl.txt met échte, betekenisvolle
Nederlandse tekst als basis, in stukken geknipt/gevarieerd zodat opeenvolgende bestanden
niet identiek zijn) tot precies size_kb kilobyte. Ondersteun filetype "txt", "pdf" en "docx"
(gebruik python-docx en reportlab of fpdf voor pdf). Voeg een CLI toe
(python generator.py --size-kb 100 --count 10 --type pdf --output-dir ...) zodat ik
reeksen kan genereren. Schrijf 1 pytest-test die verifieert dat het gegenereerde bestand
binnen 5% van de doelgrootte zit.
```

### 1.2 Scan/OCR-variant generator
**Wat we testen:** niets — infrastructuur. Zet een gegenereerde tekstfile om naar een PDF waarin de tekst als afbeelding is gerenderd (dus Tika moet OCR gebruiken), op dezelfde groottes als de tekstversie.

**Claude Code prompt:**
```
Maak tests/performance/reference_files/generator.py uit (voeg toe aan bestaand bestand)
een functie generate_scanned_pdf(size_kb: int, index: int, output_dir: Path) -> Path
die tekst uit sample_nl.txt rendert als afbeelding (bv. via PIL: tekst op een wit canvas
tekenen als bitmap) en die afbeelding(en) in een PDF plaatst, zodat er geen selecteerbare
tekstlaag in zit en Tika's OCR-pad wordt aangesproken. Zorg dat de output-grootte
vergelijkbaar is met de size_kb parameter (varieer resolutie/paginacount om dit te bereiken).
Voeg een CLI-optie toe aan de bestaande generator (--ocr-required flag).
```

### 1.3 Manifest-systeem
**Wat we testen:** niets — infrastructuur. Beschrijft welke combinatie van referentiebestanden een testrun gebruikt, zodat we niet telkens nieuwe data genereren.

**Claude Code prompt:**
```
Maak tests/performance/manifests/ met een JSON-schema voor manifests:
{
  "manifest_id": "string",
  "files": [{"size_kb": int, "count": int, "filetype": "txt|pdf|docx", "ocr_required": bool}]
}
Maak tests/performance/fixtures/assembler.py met een functie
assemble_from_manifest(manifest_path: Path, tmp_dir: Path) -> Path
die: 1) het manifest inleest, 2) voor elke file-spec de generator uit generator.py aanroept
als het bestand nog niet in reference_files/generated/ bestaat (cache op basis van
size_kb+index+filetype+ocr_required in de bestandsnaam), 3) de bestanden naar tmp_dir kopieert.
Genereer ook 3 concrete manifest-bestanden:
- batch_10files_10kb.json (10 files x 10kb, txt)
- batch_100files_10kb.json (100 files x 10kb, txt)
- batch_10files_mixed_ocr.json (10 files, helft txt helft ocr-required, 10kb elk)
Schrijf 1 test die assemble_from_manifest aanroept en verifieert dat het juiste aantal
bestanden in tmp_dir terechtkomt.
```

### 1.4 Ollama warm-up functie
**Wat we testen:** niets — infrastructuur, voorkomt dat cold-start (model laden in VRAM) je metingen vervuilt.

**Claude Code prompt:**
```
Maak tests/performance/fixtures/warmup.py met een functie
warmup_model(model_name: str, ollama_url: str) -> None
die één minimale dummy-call doet naar het opgegeven Ollama-model (bv. "geef één woord terug")
zodat het model geladen is in VRAM/geheugen vóór de echte meting start. Maak dit herbruikbaar
als pytest fixture warmed_up_model(model_name) in tests/performance/conftest.py, die warmup_model
aanroept vóór de test en de duur van de warm-up apart logt (niet meetellen in de testmeting zelf).
```

### 1.5 Timing decorator + JSONL-writer
**Wat we testen:** niets — infrastructuur, de kernlogger van de hele suite.

**Claude Code prompt:**
```
Maak tests/performance/fixtures/logger.py met:
1. Een functie get_git_commit() -> str die "git rev-parse --short HEAD" uitvoert.
2. Een functie get_db_stats(connection) -> dict die pg_database_size(datname) en
   een rijentelling (COUNT(*)) van de relevante tabellen (files, ner_results,
   summaries) ophaalt en teruggeeft als {"db_size_mb": float, "db_row_count": dict}.
3. Een functie log_benchmark(phase: str, duration_sec: float, **extra_fields) die een
   dict samenstelt met velden: timestamp (ISO), git_commit, phase, duration_sec, en
   alle extra_fields (bv. file_count, file_size_kb, total_corpus_kb, ocr_used, model_used,
   device, run_type, db_size_mb, db_row_count, manifest_id), en dit als 1 regel JSON
   append naar tests/performance/logs/benchmarks.jsonl.
4. Een context manager measure_time(phase, **extra_fields) die start/stop timet met
   time.perf_counter() en automatisch log_benchmark aanroept bij het verlaten van de
   context, ook bij een exception (log dan met duration_sec en een extra veld "failed": true).
Schrijf een unit test die verifieert dat measure_time() een correcte regel toevoegt
aan een tijdelijk logbestand.
```

---

## 2. Ingest-schaaltests (Tika)

### 2.1 Ingest schaling per bestandsgrootte
**Wat we testen:** hoe ingest-tijd schaalt bij een vast aantal bestanden (10) en oplopende grootte per bestand (1KB, 10KB, 100KB, 1MB, 10MB, 100MB — constanten in de testcode).

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_ingest_scaling_size.py. Gebruik pytest.mark.benchmark.
Definieer bovenaan het bestand een constante SIZES_KB = [1, 10, 100, 1000, 10000, 100000]
(1KB tot 100MB). Voor elke grootte: assembleer via assembler.py een manifest met 10 files
van die grootte (txt, geen ocr), roep de bestaande ingest_service (Tika-extractie) aan op
die folder, en meet de totale duur met measure_time(phase="ingest_by_size",
file_count=10, file_size_kb=<size>, total_corpus_kb=<size*10>, ocr_used=False).
Parametriseer de test met @pytest.mark.parametrize over SIZES_KB zodat elke grootte een
aparte, individueel faalbare test is (naamgeving test_ingest_size_1kb, test_ingest_size_10kb, ...).
Geen assert op een vaste drempel — dit is puur meten en loggen.
```

### 2.2 Ingest schaling per bestandsaantal
**Wat we testen:** hoe ingest-tijd schaalt bij een vaste bestandsgrootte (10KB) en oplopend aantal bestanden.

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_ingest_scaling_count.py, naar analogie van
test_ingest_scaling_size.py. Definieer COUNTS = [10, 100, 1000, 10000] als constante.
Voor elk aantal: assembleer een manifest met files van vaste grootte 10KB (txt, geen ocr),
draai ingest, meet met measure_time(phase="ingest_by_count", file_count=<count>,
file_size_kb=10, total_corpus_kb=<count*10>, ocr_used=False). Parametriseer per count
als aparte test. Waarschuw in een code-comment dat COUNTS=10000 lang kan duren en
overweeg dit als aparte, optioneel te skippen test met @pytest.mark.slow.
```

### 2.3 Ingest schaling gecombineerd (realistisch tot 1GB)
**Wat we testen:** combinatie van aantal × grootte tot een totale corpusgrootte van ~1GB, om te zien of het schaalgedrag consistent blijft op realistische totaalvolumes.

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_ingest_scaling_combined.py. Definieer een constante
COMBINATIONS = [(1000, 1000), (100, 10000), (10, 100000)] (tuples van (file_count, size_kb),
telkens neerkomend op ~1GB totaal — pas gerust de exacte tuples aan zodat totaal steeds
ongeveer 1_000_000 KB is). Voor elke combinatie: assembleer, draai ingest, meet met
measure_time(phase="ingest_combined", file_count=<n>, file_size_kb=<size>,
total_corpus_kb=<n*size>, ocr_used=False). Parametriseer als aparte tests, markeer alle
drie met @pytest.mark.slow naast @pytest.mark.benchmark.
```

### 2.4 OCR aan/uit vergelijking
**Wat we testen:** de overhead die OCR toevoegt, door dezelfde groottes/aantallen te draaien met en zonder scan-PDF (Tika detecteert OCR-noodzaak automatisch, geen aparte configuratie nodig).

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_ocr_overhead.py. Gebruik SIZES_KB = [10, 100, 1000, 10000]
en file_count=10 vast. Voor elke grootte: draai de ingest twee keer — 1x met manifest
ocr_required=False (zuivere tekst-pdf) en 1x met ocr_required=True (scan-pdf via
generate_scanned_pdf). Log beide met measure_time(phase="ingest_ocr_comparison",
file_count=10, file_size_kb=<size>, ocr_used=<True/False>). Parametriseer over SIZES_KB,
zodat elke grootte 2 losse, vergelijkbare metingen oplevert in de log.
```

---

## 3. Analyse-schaaltests

### 3.1 NER-timing schaling
**Wat we testen:** hoe NER-analysetijd schaalt met bestandsaantal en -grootte, per model (wikineural, GLiNER, Ollama few-shot), met warm-up toegepast.

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_ner_scaling.py. Gebruik de warmed_up_model fixture
uit conftest.py vóór elke meting. Definieer MODELS = ["wikineural", "gliner", "ollama_fewshot"]
en SIZES_KB = [10, 100, 1000, 10000] als constanten, file_count=10 vast. Voor elke combinatie
van model × grootte: assembleer 10 files van die grootte, draai de bestaande NER-service
(gebruik de al geïmplementeerde ner_engine per model), meet met
measure_time(phase="ner_scaling", model_used=<model>, file_count=10, file_size_kb=<size>,
run_type="warm"). Parametriseer als aparte tests per (model, size)-combinatie.
```

### 3.2 Summary-timing schaling
**Wat we testen:** hoe summary-generatietijd (Ollama) schaalt met bestandsaantal en -grootte.

**Claude Code prompt:**
```
Maak tests/performance/scaling/test_summary_scaling.py, naar analogie van
test_ner_scaling.py maar zonder model-loop (1 vast summary-model). Gebruik de
warmed_up_model fixture, SIZES_KB = [10, 100, 1000, 10000] als constante, file_count=10
vast. Voor elke grootte: assembleer, draai de bestaande summary-service, meet met
measure_time(phase="summary_scaling", file_count=10, file_size_kb=<size>, run_type="warm").
Parametriseer per size als aparte test.
```

---

## 4. Database & Query-schaaltests

### 4.1 Full-text search (tsvector) query-timing vs DB-grootte
**Wat we testen:** of full-text search-queries trager worden naarmate de DB meer records bevat (niet gemeten op een lege test-DB).

**Claude Code prompt:**
```
Maak tests/performance/queries/test_fulltext_search_scaling.py. Gebruik de bestaande
modaldb_test database. Definieer DB_ROW_COUNTS = [100, 1000, 10000] als constante.
Voor elk aantal: vul de test-DB op tot dat aantal rijen (via de bestaande ingest+NER-flow
op gegenereerde bestanden, of via directe bulk-insert als dat sneller is en de tabelstructuur
niet omzeilt op een manier die de query-test vervalst), roep dezelfde vaste full-text
search-query aan (bestaande tsvector-endpoint of repository-methode), meet met
measure_time(phase="fulltext_search", db_row_count=<n>) waarbij db_row_count en db_size_mb
automatisch via get_db_stats() worden meegelogd. Ruim de DB op tussen parametrisaties
(truncate) zodat elke test met een schone, gecontroleerde rijenteller start.
```

### 4.2 Vector search (pgvector) query-timing vs DB-grootte
**Wat we testen:** idem als 4.1 maar voor semantic/vector search — pas activeren zodra `dieter/semsearch` hervat is.

**Claude Code prompt:**
```
Maak tests/performance/queries/test_vector_search_scaling.py, structureel identiek aan
test_fulltext_search_scaling.py maar met phase="vector_search" en de pgvector cosine-similarity
query in plaats van tsvector. Gebruik dezelfde DB_ROW_COUNTS = [100, 1000, 10000] constante
en dezelfde meet/opruim-aanpak. Markeer het bestand met een skip-conditie
(@pytest.mark.skipif) als de embeddings-kolom nog niet bestaat in het schema, zodat dit
pas actief wordt zodra de semsearch-migratie gemerged is.
```

---

## 5. Realistische validatie (apart van de synthetische grid)

### 5.1 Archief-statistiekscript
**Wat we testen:** niets direct — analyseert een écht archief om te checken of de synthetische testgrid (SIZES_KB, COUNTS) representatief is voor wat klanten werkelijk aanleveren.

**Claude Code prompt:**
```
Maak tests/performance/realistic/archive_stats.py met een CLI-script dat een pad naar
een échte archief-folder (bv. het VEA260 archief) als argument neemt, recursief alle
bestanden scant, en een rapport genereert (print + JSON-output naar
tests/performance/logs/archive_stats_<naam>.json) met: totaal aantal bestanden, totale
grootte, histogram van bestandsgroottes (bins: <10KB, 10-100KB, 100KB-1MB, 1-10MB, >10MB),
verdeling per bestandstype (extensie), en gemiddelde/mediaan/max bestandsgrootte.
Gebruik dit niet om nieuwe automatische tests te genereren — het is puur een
analyse-hulpmiddel om te bepalen of de constanten in scaling/*.py realistisch zijn.
```

### 5.2 Fixed realistische test-snapshot
**Wat we testen:** sanity-check — presteert het systeem op échte data zoals verwacht op basis van de synthetische curves?

**Claude Code prompt:**
```
Maak tests/performance/realistic/test_realistic_snapshot.py. Kopieer een vaste,
representatieve substeekproef van een écht archief (bv. 50 bestanden uit VEA260, manueel
gekozen of via een vast seed/selectie) naar tests/performance/reference_files/realistic_snapshot/
(commit dit in git als vaste testdata, na controle dat er geen gevoelige/vertrouwelijke
inhoud in zit). Schrijf 1 test die de volledige ingest+NER+summary-flow op deze snapshot
draait en logt met measure_time(phase="realistic_snapshot", file_count=50,
total_corpus_kb=<werkelijke grootte>). Dit is een validatiepunt, geen curve-fit-input —
voeg een code-comment toe die dit onderscheid expliciet maakt.
```

---

## 6. Analyse & plotting

### 6.1 Plot-script
**Wat we testen:** niets — verwerkt de verzamelde JSONL-data tot visualisaties en curve-fits voor extrapolatie.

**Claude Code prompt:**
```
Maak tests/performance/analysis/plot_benchmarks.py met een CLI-script dat
tests/performance/logs/benchmarks.jsonl inleest via pandas (pd.read_json met lines=True),
en per "phase" een figuur genereert (matplotlib) met:
1. duration_sec vs file_size_kb (log-log schaal), met een gefitte curve
   (probeer lineair en power-law fit via numpy.polyfit op log-log data, toon beide R²)
2. duration_sec vs file_count (log-log schaal), zelfde fit-aanpak
3. Voor phase="fulltext_search" en "vector_search": duration_sec vs db_row_count
Sla de figuren op als PNG in tests/performance/logs/plots/<phase>_<timestamp>.png.
Print ook de fit-parameters (zodat extrapolatie naar bv. 1GB/10.000 files mogelijk is
zonder de plot te hoeven aflezen).
```
