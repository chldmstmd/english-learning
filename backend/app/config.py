from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Provider credentials/models now live with the translation-service; the
    # backend only talks to it over HTTP via translation_service_url.
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/english_learning",
        alias="DATABASE_URL",
    )
    translation_service_url: str = Field(
        "http://127.0.0.1:8001",
        alias="TRANSLATION_SERVICE_URL",
    )
    secret_key: str = Field("change-this-in-production-use-env-var", alias="SECRET_KEY")
    access_token_expire_days: int = 7

    model_config = {
        "env_file": (".env", "backend/.env"),
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = Settings()
