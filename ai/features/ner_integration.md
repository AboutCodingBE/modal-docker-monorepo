# NER integration
The NER feature was developed in isolation. For proper integration in the task system, we need to make a few changes. 

The full list of changes needed:
                                                                                                                                                                                                            
---                                                                                                                                                                                                       
1. Delete create_ner_for_archive/router.py and remove it from main.py                                                                                                                                     
   The /api/ner/{archive_id} endpoint is replaced entirely by the existing /api/analysis/start. In main.py, remove the import of ner_router and its app.include_router(ner_router) line.

  ---                                                                                                                                                                                                       
2. Update analysis/start_router.py
- Add "ner" to _SUPPORTED_TYPES
- Add type to the jobs tuple (currently it's (archive_id, archive_analysis_id, task_id, model) — type is missing, so there's no way to dispatch)
- Update _run_sequential() to dispatch to CreateNerForArchive or CreateSummariesForArchive based on the type
- Import CreateNerForArchive

  ---                                                                                                                                                                                                       
3. Refactor create_ner_for_archive/create_ner_for_archive.py                                                                                                                                              
   Still uses the old connection-leak pattern — takes a session in __init__ instead of session_factory. Needs the same refactor we applied to summaries: accept session_factory, use short-lived sessions per
   DB operation, release the connection during asyncio.to_thread(run_ner, ...). Also replace all print() calls with a proper logger (app.ner or app).

  ---
4. Fix field name mismatch between the model and the migration                                                                                                                                            
   The migration (which you just updated) uses persons_count and locations_count (plural). But models.py, ner_repository.py, and ner_engine.py all still use person_count and location_count (singular). All
   three need to align with the migration's plural names.

  ---
5. Fix Ner model in models.py                                                                                                                                                                             
   parent_folder_id is declared nullable=False with no FK — but the migration now has ForeignKey("files.id", ondelete="SET NULL"), nullable=True. The model needs to match: add the FK and change to         
   nullable=True.