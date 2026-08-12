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

    embedding_model: str = "qwen3-embedding-0.6b"
    # Moet gelijk blijven aan de VECTOR(n)-kolom in migratie 0010. Wordt momenteel nergens
    # gecheckt bij opstart — zie TODO in 0010_add_embeddings_table.py (open beslissing, Nicholas).
    embedding_dimension: int = 1024
    embedding_chunk_size: int = 512


settings = Settings()
