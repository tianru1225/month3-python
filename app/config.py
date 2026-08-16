from pydantic import Field, SecretStr
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

    llm_retry_max_attempts: int = Field(default=3, ge=1, le=5)
    llm_retry_base_delay_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    llm_retry_max_delay_seconds: float = Field(default=8.0, gt=0.0, le=300.0)
    llm_max_concurrency: int = Field(default=2, ge=1, le=64)
    llm_max_waiting: int = Field(default=4, ge=0, le=1000)

    llm_structured_max_repairs: int = Field(default=1, ge=0, le=3)

    dashscope_api_key: SecretStr = SecretStr("")
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.8-max"
    qwen_connect_timeout_seconds: float = 10.0
    qwen_read_timeout_seconds: float = 240.0
    qwen_write_timeout_seconds: float = 30.0
    qwen_pool_timeout_seconds: float = 10.0
    qwen_max_output_tokens: int = Field(default=600, ge=1, le=32768)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", validate_assignment=True
    )


settings = Settings()
