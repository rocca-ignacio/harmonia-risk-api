from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_PATH: str = "harmonia.db"
    RULES_CACHE_TTL_SECONDS: int = 300
    BLOCKLIST_CACHE_TTL_SECONDS: int = 60
    MAX_RESPONSE_TIME_MS: int = 200

    model_config = {"env_prefix": "HARMONIA_"}


settings = Settings()
