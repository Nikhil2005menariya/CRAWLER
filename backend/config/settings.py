from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from backend/ regardless of CWD
_ENV_FILE = Path(__file__).parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_prefix="",
        extra="ignore",       # silently drop .env keys not declared here
    )

    # Crawler
    crawl_delay_seconds: float = 2.0
    max_concurrent_requests: int = 4
    sqlite_db_path: str = "./data/crawl.db"
    user_agent: str = "MYK-Laticrete-Crawler/0.1"
    request_timeout_seconds: int = 20

    # LLM
    gemini_api_key: str = ""

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ChromaDB
    chroma_persist_dir: str = "./data/chroma"
