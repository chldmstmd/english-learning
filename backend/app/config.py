from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    database_url: str = Field(..., alias="DATABASE_URL")
    secret_key: str = Field("change-this-in-production-use-env-var", alias="SECRET_KEY")
    access_token_expire_days: int = 7

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
