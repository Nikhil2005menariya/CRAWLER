import logging
from collections import deque
from datetime import datetime
from typing import Iterable, List, Optional, Set
from urllib.parse import urlparse

import requests

from .content_detector import (
    CONTENT_DOCX,
    CONTENT_HTML,
    CONTENT_PDF,
    detect_content_type,
)
from .dedup import compute_content_hash, is_unchanged
from .extractors import extract_docx, extract_html, extract_pdf
from .models import CrawlRecord
from .rate_limiter import RateLimiter
from .robots_handler import RobotsHandler
from .storage import CrawlStorage


class CrawlOrchestrator:
    def __init__(
        self,
        storage: CrawlStorage,
        rate_limiter: RateLimiter,
        robots_handler: RobotsHandler,
        user_agent: str,
        request_timeout_seconds: int = 20,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.storage = storage
        self.rate_limiter = rate_limiter
        self.robots_handler = robots_handler
        self.user_agent = user_agent
        self.request_timeout_seconds = request_timeout_seconds
        self.session = session or requests.Session()
        self._logger = logging.getLogger(__name__)

    def crawl_batch(self, urls: Iterable[str]) -> List[CrawlRecord]:
        queue = deque(urls)
        seen: Set[str] = set()
        allowed_domains = {urlparse(url).netloc for url in urls if urlparse(url).netloc}
        records: List[CrawlRecord] = []

        while queue:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if not self.robots_handler.is_allowed(url):
                self._logger.info("Blocked by robots.txt: %s", url)
                continue

            record = self._crawl_url(url)
            if not record:
                continue

            records.append(record)
            if record.content_type == CONTENT_HTML and record.discovered_urls:
                queue.extend(self._filter_discovered(record.discovered_urls, allowed_domains))

        return records

    def _crawl_url(self, url: str) -> Optional[CrawlRecord]:
        self._logger.info("🕷️ Fetching: %s", url)
        headers = {"User-Agent": self.user_agent}
        with self.rate_limiter.limit():
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=self.request_timeout_seconds,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                self._logger.warning("❌ Request failed: %s (%s)", url, exc)
                return None

        content_type = detect_content_type(url, response.headers)
        if response.status_code >= 400:
            self._logger.warning("❌ Non-OK response: %s (status=%s)", url, response.status_code)
            return None

        if content_type == CONTENT_HTML:
            text, discovered_urls, title = extract_html(response.text, response.url)
        elif content_type == CONTENT_PDF:
            text = extract_pdf(response.content)
            discovered_urls, title = [], None
        elif content_type == CONTENT_DOCX:
            text = extract_docx(response.content)
            discovered_urls, title = [], None
        else:
            self._logger.info("⚠️ Unsupported content type for %s", url)
            return None

        content_hash = compute_content_hash(text)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        previous_hash, previous_etag = self.storage.get_latest_fingerprint(url)
        unchanged = is_unchanged(previous_hash, previous_etag, content_hash, etag)

        record = CrawlRecord(
            url=url,
            fetched_at=datetime.utcnow(),
            status_code=response.status_code,
            content_type=content_type,
            content_hash=content_hash,
            text=text,
            title=title,
            discovered_urls=discovered_urls,
            etag=etag,
            last_modified=last_modified,
        )
        self.storage.save_history(record, unchanged)
        if unchanged:
            self._logger.info("  → Content unchanged (skipped): %s", url)
            return None

        self.storage.save_record(record)
        self._logger.info("  ✅ Crawled successfully: %s (type=%s, hash=%s)", url, content_type, content_hash[:8])
        return record

    # URL path prefixes that contain product or document content worth crawling
    _PRODUCT_PATH_PREFIXES = (
        "/products/",
        "/downloads/",
        "/solutions-by-applications/",
        "/challenges-and-solutions/",
        "/blog/",
    )

    def _filter_discovered(self, urls: List[str], allowed_domains: Set[str]) -> List[str]:
        filtered: List[str] = []
        for link in urls:
            if not self._is_allowed_domain(link, allowed_domains):
                continue
            parsed = urlparse(link)
            content_type = detect_content_type(link, None)
            # For HTML pages: only follow links under known product/content paths
            if content_type == CONTENT_HTML:
                if any(parsed.path.startswith(prefix) for prefix in self._PRODUCT_PATH_PREFIXES):
                    filtered.append(link)
            # Always follow PDF/DOCX files (data sheets etc.)
            elif content_type in {CONTENT_PDF, CONTENT_DOCX}:
                filtered.append(link)
        return filtered

    @staticmethod
    def _is_allowed_domain(url: str, allowed_domains: Set[str]) -> bool:
        netloc = urlparse(url).netloc
        return not allowed_domains or netloc in allowed_domains
