"""Central app configuration, loaded from backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),  # backend/.env
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Azure OpenAI ---
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # --- Qdrant ---
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection_name: str = "enterprise-rag"

    # --- Cohere (reserved for v2) ---
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-multilingual-v2.0"

    # --- MySQL ---
    database_url: str = "mysql+pymysql://root:root@localhost:3306/ragdb"

    # --- Auth (reserved for v3) ---
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- App ---
    app_env: str = "development"
    upload_dir: str = "./data/uploads"
    log_level: str = "INFO"

    # --- Chunking ---
    chunk_target_tokens: int = 500
    chunk_overlap_tokens: int = 50

    # --- Retrieval ---
    default_top_k: int = 5

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
