from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "default app"
    app_version: str = "0.0.0"
    app_env: str = "local"
    app_debug: bool = False
    api_key: str="dev-secret"
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()