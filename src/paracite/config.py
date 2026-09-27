from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ParaCite"
    version: str = "0.1.0"
    host: str = Field(default="0.0.0.0", alias="PARACITE_HOST")
    port: int = Field(default=18741, alias="PARACITE_PORT")
    public_base_url: str = Field(default="http://127.0.0.1:18741", alias="PUBLIC_BASE_URL")

    database_url: str = Field(default="sqlite:///./paracite.db", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")

    demo_api_key: str = Field(default="pc_demo_dev_key", alias="PARACITE_DEMO_API_KEY")
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    enable_ingest: bool = Field(default=False, alias="ENABLE_INGEST")

    weknora_url: str = Field(default="", alias="WEKNORA_URL")
    weknora_api_key: str = Field(default="", alias="WEKNORA_API_KEY")
    weknora_kb_id: str = Field(default="", alias="WEKNORA_KB_ID")

    jev_api_key: str = Field(default="", alias="JEV_API_KEY")
    jev_api_url: str = Field(default="https://api.typesafe.ai/v1/system_one", alias="JEV_API_URL")
    jev_model: str = Field(default="jev-1.13.0", alias="JEV_MODEL")

    corpus_dir: str = Field(default="corpus", alias="PARACITE_CORPUS_DIR")
    # Carga continua: 0 = desactivada (por defecto). En producción, p. ej. 168 (semanal).
    ingest_interval_hours: float = Field(default=0, alias="PARACITE_INGEST_INTERVAL_HOURS")
    ingest_first_delay_s: float = Field(default=300, alias="PARACITE_INGEST_FIRST_DELAY_S")

    retrieval_top_k: int = 40
    default_umbral: float = 0.87
    default_jurisdiccion: str = "ES"


@lru_cache
def get_settings() -> Settings:
    return Settings()
