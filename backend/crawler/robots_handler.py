import logging
import time
from typing import Dict, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests


class RobotsHandler:
    def __init__(
        self,
        user_agent: str,
        session: requests.Session | None = None,
        cache_ttl_seconds: int = 86_400,
    ) -> None:
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._parsers: Dict[str, Tuple[RobotFileParser, float]] = {}
        self._logger = logging.getLogger(__name__)

    def is_allowed(self, url: str) -> bool:
        base_url = self._base_url(url)
        parser = self._get_parser(base_url)
        return parser.can_fetch(self.user_agent, url)

    def _get_parser(self, base_url: str) -> RobotFileParser:
        now = time.monotonic()
        cached = self._parsers.get(base_url)
        if cached and now - cached[1] < self.cache_ttl_seconds:
            return cached[0]

        robots_url = f"{base_url}/robots.txt"
        parser = RobotFileParser()
        try:
            response = self.session.get(robots_url, timeout=10)
            if response.status_code >= 400:
                self._logger.info(
                    "robots.txt unavailable: %s (status=%s)",
                    robots_url,
                    response.status_code,
                )
                parser.parse([])
            else:
                parser.parse(response.text.splitlines())
        except requests.RequestException as exc:
            self._logger.warning("robots.txt fetch failed: %s (%s)", robots_url, exc)
            parser.parse([])

        self._parsers[base_url] = (parser, now)
        return parser

    @staticmethod
    def _base_url(url: str) -> str:
        parts = urlparse(url)
        return f"{parts.scheme}://{parts.netloc}"
