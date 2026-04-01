from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODAL_DB_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    name: str = "modaldb"
    user: str = "user"
    password: str = "password"

    @property
    def url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


db_settings = DatabaseSettings()
