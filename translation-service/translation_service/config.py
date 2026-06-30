from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


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

    model_config = {
        "env_file": (".env", "translation-service/.env"),
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = Settings()
