## Database Tables Summary

### `archives`
Top-level entity representing an analyzed archive/directory.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| name | String(255) | |
| root_path | String(1000) | Unique |
| analysis_status | String(20) | pending/in_progress/completed/failed |
| analysis_started_at | DateTime | Nullable |
| analysis_completed_at | DateTime | Nullable |
| error_message | Text | Nullable |
| description | Text | Nullable |
| file_count | Integer | Default 0 |
| directory_count | Integer | Default 0 |
| total_size_bytes | BigInteger | Default 0 |
| created_at | DateTime | Server default now() |

---

### `files`
Every file and directory discovered within an archive (self-referencing tree).
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| archive_id | UUID | FK → archives (CASCADE) |
| parent_id | UUID | FK → files (CASCADE), nullable |
| name | String(500) | |
| full_path | String(2000) | |
| relative_path | String(2000) | |
| is_directory | Boolean | |
| extension | String(50) | Nullable, NULL if directory |
| size_bytes | BigInteger | Nullable, NULL if directory |
| sha256_hash | String(64) | Nullable |
| created_at | DateTime | Nullable (filesystem timestamp) |
| modified_at | DateTime | Nullable (filesystem timestamp) |
| discovered_at | DateTime | Server default now() |

---

### `analysis_tasks`
Tracks background processing jobs run against an archive.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| archive_id | UUID | FK → archives (CASCADE) |
| status | String(20) | pending/running/completed/failed |
| task_type | String(20) | Default "analysis" |
| total_files | Integer | |
| processed | Integer | |
| failed_count | Integer | |
| current_file | Text | Nullable |
| created_at | DateTime | Server default now() |
| started_at | DateTime | Nullable |
| completed_at | DateTime | Nullable |

---

### `tika_analyses`
Apache Tika extraction results per file (1:1 with files).
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| file_id | UUID | FK → files (CASCADE), unique |
| mime_type | String(255) | Nullable |
| tika_parser | Text | Nullable |
| content | Text | Nullable |
| language | String(10) | Nullable |
| word_count | Integer | Nullable |
| author | String(500) | Nullable |
| content_created_at | DateTime | Nullable |
| analyzed_at | DateTime | Server default now() |

---

### `generic_types`
Generic file type classification per file (1:1 with files).
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| file_id | UUID | FK → files (CASCADE), unique |
| archive_id | UUID | FK → archives (CASCADE) |
| generic_type | String(255) | Nullable |
| analyzed_at | DateTime | Server default now() |

---

### `processing_settings`
Global configuration for AI processing limits.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| summary_char_limit | Integer | Default 1000 |
| topic_char_limit | Integer | Default 1000 |
| ner_llm_char_limit | Integer | Default 6000 |
| minimum_text_length | Integer | Default 0 |

---

### `analysis_configuration`
Defines which AI model to use per analysis type.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| type | Enum | STT / NER / SUMMARY / TOPIC_DETECTION |
| model | String(255) | |
| is_default | Boolean | Default false |

---

### `archive_analysis`
Tracks a specific analysis run (by type) on an archive.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| archive_id | UUID | FK → archives (CASCADE) |
| type | Enum | STT / NER / SUMMARY / TOPIC_DETECTION |
| date | Date | Server default current_date() |
| model | String(255) | |
| status | Enum | STARTED / FAILED / COMPLETED / CANCELLED |

---

### `summary`
AI-generated summaries per file or folder within an analysis run.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| analysis_id | UUID | FK → archive_analysis (CASCADE) |
| archive_id | UUID | FK → archives (CASCADE) |
| parent_folder_id | UUID | FK → files (SET NULL), nullable |
| file_id | UUID | FK → files (SET NULL), nullable |
| result | Text | Nullable |

---

### `ner`
Named Entity Recognition results per file.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| archive_id | UUID | FK → archives (CASCADE) |
| analysis_id | UUID | FK → archive_analysis (CASCADE) |
| parent_folder_id | UUID | FK → files (SET NULL), nullable |
| file_id | UUID | FK → files (CASCADE) |
| persons | JSONB | Array, default [] |
| locations | JSONB | Array, default [] |
| organisations | JSONB | Array, default [] |
| misc | JSONB | Array, default [] |

---

### `topic_detection`
Topic detection results per file.
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| archive_id | UUID | FK → archives (CASCADE) |
| analysis_id | UUID | FK → archive_analysis (CASCADE) |
| parent_folder_id | UUID | FK → files (SET NULL), nullable |
| file_id | UUID | FK → files (CASCADE) |
| topics | JSONB | Array, default [] |
