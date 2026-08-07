from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "default app"
    app_version: str = "0.0.0"
    app_env: str = "local"
    app_debug: bool = False
    api_key: str = "dev-secret"
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_connect_timeout_seconds: float = 10.0
    ollama_read_timeout_seconds: float = 240.0
    ollama_write_timeout_seconds: float = 30.0
    ollama_pool_timeout_seconds: float = 10.0
    ollama_num_predict: int = 300
    ollama_num_ctx: int = 4096
    llm_retry_max_attempts: int = Field(default=3, ge=1, le=5)
    llm_retry_base_delay_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    llm_retry_max_delay_seconds: float = Field(default=8.0, gt=0.0, le=300.0)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
