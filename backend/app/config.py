from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field


class Settings(BaseSettings):
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    deepseek_api_key: str = Field(
        "",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "deepseek_api_key"),
    )
    deepseek_model: str = Field(
        "deepseek-v4-flash",
        validation_alias=AliasChoices("DEEPSEEK_MODEL", "deepseek_model"),
    )
    deepseek_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "deepseek_base_url"),
    )
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/english_learning",
        alias="DATABASE_URL",
    )
    secret_key: str = Field("change-this-in-production-use-env-var", alias="SECRET_KEY")
    access_token_expire_days: int = 7

    model_config = {
        "env_file": (".env", "backend/.env"),
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = Settings()
