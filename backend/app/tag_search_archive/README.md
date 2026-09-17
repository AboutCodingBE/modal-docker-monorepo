# tag_search_archive — te bouwen door Nicholas

## Wat er al klaar staat (niet meer aan te passen, enkel te gebruiken)

`TagIndexRepository` (in `backend/app/create_tag_index_for_archive/tag_index_repository.py`)
heeft 3 kant-en-klare zoekmethodes, elk met tests in `backend/tests/integration/`:

- `search(archive_id, prefix, top_n)` — typeahead, prefix-`ILIKE`. Test: `test_M8_01_tagsearch_repository_search.py`
- `search_by_tags(archive_id, values, top_n, match="any"|"all")` — multi-tag filter (OR/AND). Test: `test_M8_02_tagsearch_repository_search_by_tags.py`
- `get_all_tags(archive_id, category=None)` — alle unieke tags, voor het vullen van een filterpaneel. Test: `test_M8_03_tagsearch_repository_get_all_tags.py`

Alle 3 geven dezelfde soort output terug: een lijst van dicts met `value`, `source`,
`category`, en (bij `search`/`search_by_tags`) `file_id`/`file_name`/`relative_path`/`is_directory`.

## Wat hier nog moet komen

**1. `tag_search_archive.py`** — een klasse `TagSearchArchive` met `.execute()`, exact
naar het patroon van `GetNerForFile` in `backend/app/get_ner_for_file/get_ner_for_file.py`
(lezen als voorbeeld!). Minimaal voor de typeahead-zoekbalk:

```python
class TagSearchArchive:
    def __init__(self, session):
        self._session = session

    async def execute(self, archive_id, query, top_n) -> list[dict] | None:
        # 1. check of archive_id bestaat (select(Archive.id).where(...)) -> None als niet
        # 2. zo ja: return await TagIndexRepository(self._session).search(archive_id, query, top_n)
```

Referentie voor het 404-patroon: `origin/dieter/semsearch:backend/app/search_archive/search_archive.py`
(`git show` die branch om te bekijken).

**2. `router.py`** — analoog aan `search_archive/router.py` uit diezelfde branch:
```python
router = APIRouter(prefix="/api/archives", tags=["tag-search"])

@router.get("/{archive_id}/tags/search")
async def search_tags(archive_id: UUID, q: str = Query(..., min_length=1),
                       top_n: int = Query(default=settings.tag_search_top_n, ge=1),
                       db=Depends(get_db)):
    result = await TagSearchArchive(db).execute(archive_id, q, top_n)
    if result is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return result
```

Vergeet niet: `tag_search_top_n: int = 25` toevoegen aan `Settings` in `backend/app/config.py`
(zelfde stijl als `ner_folder_top_n`), en de router registreren in `backend/app/main.py`
(`app.include_router(tag_search_router)`).

**3. Tests** — zelfde M8-nummering, doorlopend:
- `test_M8_04_tagsearch_use_case_404.py` (integration) — onbestaand archief → `None`
- `test_M8_05_tagsearch_router.py` (integration) — FastAPI `TestClient`: 200 + juiste shape,
  404 bij onbestaand archief, 422 bij ontbrekende `q`

## Nog geen endpoint voor `search_by_tags`/`get_all_tags`

Bewust uitgesteld tot het multi-tag filterscherm concreet is — dan weten we welke
queryparameters de router nodig heeft (lijst van tags in de URL, hoe `match` doorgeven, enz.).
De repository-methodes staan al klaar, enkel de use-case/router-laag ontbreekt daarvoor nog.

## Volledig plan

Zie `C:\Users\drdwi\.claude\plans\tidy-knitting-sutherland.md` voor de volledige context
en alle eerdere fases (tag_index-tabel + het vullen ervan vanuit NER/topic-detection).
