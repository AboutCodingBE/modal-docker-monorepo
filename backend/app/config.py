from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://archiveuser:archivepass@db:5432/archivedb"
    tika_url: str = "http://tika:9998"
    agent_url: str = "http://host.docker.internal:9090"


settings = Settings()
