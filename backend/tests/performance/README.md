# Performance Benchmark Suite

Reproduceerbare, timestamped timing-metingen van ingest, analyses en queries op
schalende testdata, weggeschreven als append-only log (JSONL) voor latere
plotting en regressie-detectie.

Dit is **geen unit test suite** (correctheid) maar een **benchmark suite**
(snelheid). Aparte map, aparte pytest-marker (`benchmark`), niet in de normale
CI-run.

De volledige specificatie — inclusief het "Wat we testen" per onderdeel en de
Claude Code-prompt om het te implementeren — staat in
[`MODAL_performance_benchmarks.md`](../../../MODAL_performance_benchmarks.md)
in de repo-root. Dit README is enkel een korte wegwijzer; dat bestand is de
bron van waarheid.

## Status

Deze map is momenteel **scaffolding**: elk bestand bevat een module-docstring
(scenario + vereiste services, in de stijl van [`tests/TESTING.md`](../TESTING.md))
en een `TODO`-commentaarblok met de bijhorende Claude Code-prompt uit
`MODAL_performance_benchmarks.md`. De prompts worden nadien één voor één
uitgerold — geen enkele test hieronder is al functioneel.

## Draaien

```bash
pytest tests/performance/ -m benchmark
```

Normale CI-runs (`pytest tests/`) sluiten `benchmark`-gemarkeerde tests
standaard uit (zie `backend/pytest.ini`).

## Structuur

```
tests/performance/
├── reference_files/    # generator voor unieke NL-testbestanden op exacte grootte
├── manifests/          # testcombinaties (count x size) als JSON
├── fixtures/            # warm-up, manifest-assembler, JSONL-logger
├── conftest.py          # gedeelde fixtures (o.a. warmed_up_model)
├── logs/                # benchmarks.jsonl — WEL committen (historiek!)
├── scaling/             # ingest/NER/summary schaaltests
├── queries/             # full-text en vector search schaaltests
├── realistic/           # validatie op een échte archiefsteekproef
└── analysis/            # plot_benchmarks.py — JSONL -> grafieken + curve-fit
```
