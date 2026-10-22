from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# One place to change the product name.
PRODUCT_NAME = "Policy Diff"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    admin_email: str = ""
    admin_password: str = ""
    models_config: str = "/config/models.yaml"
    embed_dims: int = 1536
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    session_max_age_seconds: int = 60 * 60 * 12
    cookie_secure: bool = False  # set true when served over HTTPS
    files_dir: str = "/data/files"  # uploaded PDFs and parser output
    samples_dir: str = "/samples"  # optional read-only folder with the Northwind demo corpus
    max_upload_mb: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
