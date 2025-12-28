from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://smartcart:smartcart@localhost:5432/smartcart"
    database_url_sync: str = "postgresql://smartcart:smartcart@localhost:5432/smartcart"

    # SuperValu credentials
    supervalu_email: str = ""
    supervalu_password: str = ""

    # Scheduler
    scrape_hour: int = 22
    scrape_minute: int = 0

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Dashboard
    dashboard_port: int = 8501
    api_base_url: str = "http://localhost:8000"


settings = Settings()
