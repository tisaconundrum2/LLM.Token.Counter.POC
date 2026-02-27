from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://ums_user:ums_pass@localhost:5432/ums_db"
    app_title: str = "LLM Token Counter Middleware"
    app_version: str = "1.0.0"


settings = Settings()
