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


settings = Settings()
