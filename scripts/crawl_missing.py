#!/usr/bin/env python
"""
crawl_missing.py
Crawls all product URLs that have been discovered from category pages
but not yet fetched, WITHOUT triggering any LLM parsing.
Run this to get a full picture of how many products exist on the site.
"""
import sys, sqlite3, json, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("crawl_missing")

from backend.crawler.spider import CrawlOrchestrator
from backend.crawler.storage import CrawlStorage
from backend.crawler.rate_limiter import RateLimiter
from backend.crawler.robots_handler import RobotsHandler
from backend.config.settings import Settings

settings = Settings()
db_path = settings.sqlite_db_path

# --- Step 1: Find all product URLs discovered but not yet crawled ---
conn = sqlite3.connect(db_path)
crawled = set(r[0].rstrip("/") + "/" for r in conn.execute("SELECT url FROM crawl_records").fetchall())
all_discovered = set()
for row in conn.execute("SELECT discovered_urls FROM crawl_records WHERE discovered_urls IS NOT NULL").fetchall():
    try:
        for u in json.loads(row[0]):
            if u.startswith("https://myklaticrete.com/products/"):
                all_discovered.add(u.rstrip("/") + "/")
    except Exception:
        pass
conn.close()

urls_to_crawl = sorted(all_discovered - crawled)
logger.info("Found %d product URLs not yet crawled", len(urls_to_crawl))
for u in urls_to_crawl:
    logger.info("  - %s", u)

if not urls_to_crawl:
    logger.info("Nothing to crawl — all discovered product URLs are already in crawl_records!")
    sys.exit(0)

# --- Step 2: Crawl them (no parsing) ---
storage = CrawlStorage(db_path)
rate_limiter = RateLimiter(settings.crawl_delay_seconds, max_concurrent=1)
robots = RobotsHandler(settings.user_agent)
spider = CrawlOrchestrator(storage, rate_limiter, robots, settings.user_agent)

logger.info("Starting crawl of %d URLs...", len(urls_to_crawl))
records = spider.crawl_batch(urls_to_crawl)
logger.info("Crawl complete! %d new records fetched.", len(records))

# --- Step 3: Final tally ---
conn = sqlite3.connect(db_path)
total_crawled = conn.execute("SELECT COUNT(*) FROM crawl_records").fetchone()[0]
total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

# How many are still unparsed?
parsed_urls = set()
for row in conn.execute("SELECT data_json FROM products").fetchall():
    data = json.loads(row[0])
    for u in (data.get("source_urls") or []):
        parsed_urls.add(u.rstrip("/") + "/")
all_crawled_urls = set(r[0].rstrip("/") + "/" for r in conn.execute(
    "SELECT url FROM crawl_records WHERE url LIKE '%myklaticrete.com/products/%'"
).fetchall())
conn.close()

unparsed = all_crawled_urls - parsed_urls
logger.info("=== FINAL SUMMARY ===")
logger.info("Total crawl_records (all product pages): %d", len(all_crawled_urls))
logger.info("Total parsed products in DB:             %d", total_products)
logger.info("Product pages NOT yet parsed:            %d", len(unparsed))
logger.info("")
logger.info("=== UNPARSED PRODUCT PAGES ===")
for u in sorted(unparsed):
    logger.info("  ❌ %s", u)
