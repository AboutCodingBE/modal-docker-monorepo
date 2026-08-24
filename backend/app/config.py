from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://archiveuser:archivepass@db:5432/modaldb"
    tika_url: str = "http://tika:9998"
    agent_url: str = "http://host.docker.internal:9090"
    ollama_url: str = "http://ollama:11434"
    ner_folder_top_n: int = 25
    topic_folder_top_n: int = 25

    # Ollama-tagnotatie (dubbele punt), niet "qwen3-embedding-0.6b" — zie `ollama list`.
    embedding_model: str = "qwen3-embedding:0.6b"
    # embedding_dimension moet gelijk blijven aan de VECTOR(n)-kolom in migratie 0017. Wordt momenteel nergens
    # gecheckt bij opstart — zie TODO in 0017_add_embeddings_table.py (open beslissing, Nicholas).
    embedding_dimension: int = 1024

    # Aantal woorden per chunk (whitespace-gescheiden), geen echte tokens
    embedding_chunk_size: int = 512

    # None = geen limiet, chunkt het volledige bestand. Voorlopig op 1 gezet om het testen
    # tijdens de opbouw van de pipeline te versnellen — later terug naar None (of hoger).
    # TODO (@Nicholas): dit hoort waarschijnlijk in processing_settings (DB-backed, net als
    # ner_llm_char_limit/summary_char_limit/topic_char_limit) i.p.v. hier als env-setting,
    # zodat het runtime aanpasbaar is via de UI. Vergt een aparte migratie — nu bewust simpel gehouden.
    embedding_max_chunks_per_file: int | None = 1


settings = Settings()
