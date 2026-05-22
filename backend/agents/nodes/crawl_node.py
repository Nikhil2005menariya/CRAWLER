from ..state import IngestionState
from ...config.settings import Settings
from ...crawler.rate_limiter import RateLimiter
from ...crawler.robots_handler import RobotsHandler
from ...crawler.spider import CrawlOrchestrator
from ...crawler.storage import CrawlStorage


def crawl_node(state: IngestionState) -> IngestionState:
    settings = Settings()
    storage = CrawlStorage(settings.sqlite_db_path)
    rate_limiter = RateLimiter(
        min_delay_seconds=settings.crawl_delay_seconds,
        max_concurrent=settings.max_concurrent_requests,
    )
    robots_handler = RobotsHandler(settings.user_agent)
    orchestrator = CrawlOrchestrator(
        storage=storage,
        rate_limiter=rate_limiter,
        robots_handler=robots_handler,
        user_agent=settings.user_agent,
        request_timeout_seconds=settings.request_timeout_seconds,
    )

    records = orchestrator.crawl_batch(state.get("urls_to_crawl", []))
    next_state = dict(state)
    next_state["crawl_records"] = records
    return next_state
