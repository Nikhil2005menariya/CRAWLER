from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="")

    crawl_delay_seconds: float = 2.0
    max_concurrent_requests: int = 4
    sqlite_db_path: str = "./data/crawl.db"
    user_agent: str = "MYK-Laticrete-Crawler/0.1"
    request_timeout_seconds: int = 20
