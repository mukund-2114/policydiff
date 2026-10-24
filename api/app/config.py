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
    storage_backend: str = "local"  # "local" (a folder) or "s3" (any S3-compatible bucket)
    files_dir: str = "/data/files"  # the folder, when storage_backend is local
    s3_bucket: str = "policydiff"
    s3_endpoint_url: str = ""  # MinIO or R2 address; leave empty for AWS
    s3_region: str = ""
    s3_access_key: str = ""  # leave both empty to use the machine's IAM role
    s3_secret_key: str = ""
    samples_dir: str = "/samples"  # optional read-only folder with the Northwind demo corpus
    max_upload_mb: int = 25
    # Chunking. Moves to the per-workspace settings table in S13.
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()
