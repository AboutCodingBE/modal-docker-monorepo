# TESTING — Developer Reference

Beknopte referentie voor het schrijven van tests in het MODAL-project.
Geen tutorial — voor uitleg over de gebruikte technieken, zie de inline commentaren in de testbestanden zelf.

---

## Mappenstructuur

```
tests/
├── unit/               # pure logica, geen I/O, geen database
├── integration/        # één of meerdere services + database
├── e2e/                # volledige stack, end-to-end scenario's
├── kpi/                # kwaliteitsmetrieken op echte archiefdata (zie §KPI)
├── testdata/
│   ├── data_M1/        # fixture-bestanden voor create_archive tests
│   ├── data_M2/        # PDF, DOCX, afbeeldingen voor Tika tests
│   ├── data_M3/        # documenten voor NER- en summarytests
│   ├── data_M4/        # documenten voor zoektests
│   └── data_kpi/       # echte archiefdata + expert-annotaties (JSON)
└── conftest.py         # gedeelde fixtures (DB-sessie, service-checks)
```

Fixture-bestanden worden gegenereerd via `tests/testdata/create_testdata.py`
en worden mee gecommit zodat tests reproduceerbaar zijn zonder runtime-generatie.

---

## Principes

### 1. Test altijd tegen live services — geen mocks

Mock nooit een service die lokaal draaibaar is.
De agent, Tika, Ollama en de database zijn allemaal lokaal beschikbaar via `docker compose up`
en worden daarom **nooit gemocked**.

Mocks zijn alleen toegestaan voor services die structureel niet lokaal beschikbaar zijn
(bv. een externe betalingsgateway of een SaaS-API waarvoor je geen lokale instantie kunt opstarten).

### 2. FAIL met opstartinstructie — nooit SKIP

Als een vereiste service niet bereikbaar is, moet de test **falen** met een concrete foutmelding
en opstartinstructie. `pytest.skip()` is niet toegestaan: een geskipte test geeft valse zekerheid
— hij telt als "groen" terwijl er niets getest is.

```python
# In conftest.py:
@pytest.fixture()
def requires_tika(tika_available):
    if not tika_available:
        pytest.fail(
            "Tika niet bereikbaar op http://localhost:7777 — "
            "start de stack met: docker compose up"
        )
```

### 3. Bestandsnaming en nummering

- Eén scenario per bestand.
- Bestandsnamen volgen het patroon `test_M{module}_{volgnummer}_{beschrijving}.py`:
  `test_M2_01_tika_normaal_pdf.py`
- De nummering maakt de volgorde leesbaar en helpt bij het zoeken naar een specifieke test.
- Geen testklassen tenzij er significante gedeelde setup is die conftest-fixtures niet bieden.

### 4. Documentatie per bestand

Elk testbestand begint met een **module-docstring** die drie dingen doet:

1. Kadert welke applicatiecode er getest wordt (bv. `app/perform_tika_analysis/`) en wat die module doet.
2. Beschrijft het scenario van dít bestand — de "101" voor iemand die net instapt.
3. Vermeldt welke services vereist zijn om de test te draaien.

Elke testfunctie heeft een **korte docstring** (één à twee zinnen): *wat* wordt er getest
en *waarom* dat relevant is. Geen lange opsommingen — die horen in de module-docstring.

### 5. Leesbaarheid voor een junior developer

Tests zijn de documentatie van het systeem. Schrijf ze zodat een junior Python-developer
met basiskennis van async en SQL ze kan lezen en begrijpen.

**Verplicht uitleggen met inline commentaar:**

- `MagicMock` / `AsyncMock` / `patch` — wat ze doen en waarom ze hier nodig zijn
- `flush()` vs `commit()` en waarom we `rollback()` gebruiken voor cleanup
- Context managers met meerdere patches (`with (patch(...), patch(...)):`)
- Elke constructie die een normale Python-programmeur zou verrassen

Wanneer een patroon uitzonderlijk is (zoals `patch.object` op een sessie-methode), staat er
altijd een commentaar bij dat uitlegt waarom dit bewust en veilig is in deze context.

### 6. Database

- Gebruik altijd de echte **PostgreSQL**-database (zie `DATABASE_URL_SYNC` in `.env`).
- Nooit SQLite: het project gebruikt `tsvector`-indexen en Alembic-migraties
  die niet werken in SQLite.
- Elke test draait in een transactie die na afloop via `rollback()` wordt teruggedraaid.
  Geen enkele test mag data achterlaten in de database.

### 7. Testdata

Fixture-bestanden (PDF, DOCX, afbeeldingen, ...) staan in `tests/testdata/data_M{n}/`.
Genereer ze via `tests/testdata/create_testdata.py` en commit ze mee.

### 8. Code-kwaliteit in tests

Tests zijn productiecode. De standaarden van een professioneel test engineer gelden:

- Raak alleen de **publieke interface** van het systeem aan — geen overschrijven van private methoden
  of interne implementatiedetails.
- Gebruik duidelijke variabelenamen — geen `x`, `r`, `tmp`.
- Geen copy-paste: gedeelde setup hoort in een fixture of hulpfunctie.
- Assertions hebben een foutmelding die de fout beschrijft zonder de testcode op te zoeken.
- Enkelvoudige verantwoordelijkheid: één test, één scenario, één assert-blok.
- Geen overbodige abstractie: drie vergelijkbare regels zijn beter dan een hulpfunctie
  die maar één keer gebruikt wordt.


### 9. Tests zijn gemaakt om de code te doen falen!

Niet andersom. Dus we maken geen test die de perceptie wekt dat de code werkt. We scannen dus de code enkel om ze correct te kunnen gebruiken in de tests niet om tests te creeren die succesvol zijn. De beste tests zijn net diegene die irregulariteiten in de code blootleggen!!!


### 10. Volg best practices voor coding

bv geen importants midden in de code, zet ze netjes bovenaan en groepeer de standard libraries en de custom en de eigen imports.

---

## KPI-tests (`tests/kpi/`)

KPI-tests meten de **kwaliteit** van AI-componenten op echte archiefdata.
Ze zijn fundamenteel anders dan integratietests:

| Integratietest                  | KPI-test                                      |
|---------------------------------|-----------------------------------------------|
| Correct / incorrect (binair)    | Afstand van het perfecte resultaat (metriek)  |
| Assertion faalt = bug           | Score onder drempel = kwaliteitsprobleem      |
| Draait bij elke commit          | Draait periodiek of op aanvraag               |
| Testdata gegenereerd            | Testdata = echte archiefbestanden             |

### Metrieken

| Domein        | Metriek             | Drempel (conftest.py) |
|---------------|---------------------|-----------------------|
| NER           | F1-score            | `NER_F1_DREMPEL`      |
| Samenvatting  | ROUGE-1 recall      | `SUMMARY_ROUGE1_DREMPEL` |
| Zoeken        | Precision@5         | `SEARCH_PRECISION_AT_5_DREMPEL` |

Drempelwaarden worden bijgehouden in `tests/kpi/conftest.py` en zijn aanpasbaar
door domeinexperts zonder dat de testcode hoeft te wijzigen.

### Workflow voor domeinexperts

1. Voeg een archiefdocument toe aan `tests/testdata/data_kpi/`
2. Schrijf de verwachte annotaties in de bijbehorende JSON (zie module-docstring per testbestand)
3. Commit bestand + annotaties mee in de repo
4. Voer de KPI-tests uit: `pytest tests/kpi/ -v`

### KPI-tests draaien

```bash
pytest tests/kpi/ -v                  # alle KPI-tests
pytest tests/kpi/test_kpi_ner.py -v   # enkel NER
```

---

## Vereiste services per testniveau

| Niveau        | DB  | Agent | Tika | Ollama |
|---------------|:---:|:-----:|:----:|:------:|
| `unit/`       |     |       |      |        |
| `integration/`| ✓   | ✓ M1  | ✓ M2 | ✓ M3   |
| `e2e/`        | ✓   | ✓     | ✓    | ✓      |

Start alle services: `docker compose up`

---

## Gedeelde fixtures (`conftest.py`)

| Fixture             | Scope   | Doel                                                          |
|---------------------|---------|---------------------------------------------------------------|
| `async_db_session`  | functie | Async SQLAlchemy-sessie; rollback na elke test                |
| `db_conn`           | functie | Synchrone DB-verbinding; rollback na elke test                |
| `db_engine`         | sessie  | Gedeelde engine (duur om aan te maken, één keer per run)      |
| `tika_available`    | sessie  | Checkt éénmalig of Tika bereikbaar is                         |
| `requires_tika`     | functie | Faalt de test als Tika niet bereikbaar is                     |
| `agent_available`   | sessie  | Checkt éénmalig of de agent bereikbaar is                     |
| `requires_agent`    | functie | Faalt de test als de agent niet bereikbaar is                 |
