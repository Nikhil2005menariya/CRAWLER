"""
sync/delta_detector.py
───────────────────────
DeltaDetector: compares fresh CrawlRecord content hashes against what's
stored in SQLite to classify URLs as added / modified / unchanged / deleted.
"""

import logging
import sqlite3
from typing import Dict, List

logger = logging.getLogger(__name__)


class DeltaDetector:
    """
    Compares incoming crawl records against the stored hash index to detect
    what has changed since the last crawl cycle.

    Args:
        db_path: Path to the SQLite database containing crawl_records.
    """

    def __init__(self, db_path: str = "./data/crawl.db"):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_changes(self, records: list) -> Dict[str, list]:
        """
        Classify each record in `records` as added, modified, or unchanged.
        Also detects deletions — URLs previously crawled but absent from the
        incoming batch.

        Args:
            records: List of CrawlRecord objects or dicts with 'url' and
                     'content_hash' keys.

        Returns:
            dict with keys: added, modified, unchanged, deleted
        """
        result: Dict[str, list] = {
            "added": [],
            "modified": [],
            "unchanged": [],
            "deleted": [],
        }

        stored_hashes = self._get_all_hashes()
        seen_urls = set()

        for record in records:
            url   = record.url if hasattr(record, "url") else record["url"]
            chash = record.content_hash if hasattr(record, "content_hash") else record.get("content_hash", "")
            seen_urls.add(url)

            stored = stored_hashes.get(url)
            if stored is None:
                result["added"].append(record)
            elif stored != chash:
                result["modified"].append(record)
            else:
                result["unchanged"].append(record)

        # Deleted = URLs in DB that were not seen in this batch
        for url in stored_hashes:
            if url not in seen_urls:
                result["deleted"].append(url)

        logger.info(
            "DeltaDetector: added=%d modified=%d unchanged=%d deleted=%d",
            len(result["added"]), len(result["modified"]),
            len(result["unchanged"]), len(result["deleted"]),
        )
        return result

    def has_changed(self, url: str, content_hash: str) -> bool:
        """Return True if this URL has a different hash than what's stored."""
        stored = self._get_hash(url)
        return stored is None or stored != content_hash

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all_hashes(self) -> Dict[str, str]:
        """Load all stored (url, hash) pairs from crawl_records."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            rows = conn.execute("SELECT url, hash FROM crawl_records").fetchall()
            conn.close()
            return {r[0]: r[1] for r in rows if r[1]}
        except sqlite3.OperationalError:
            return {}

    def _get_hash(self, url: str) -> str | None:
        """Get the stored hash for a single URL."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            row = conn.execute(
                "SELECT hash FROM crawl_records WHERE url = ?", (url,)
            ).fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.OperationalError:
            return None

    def get_all_urls(self) -> List[str]:
        """Return all crawled URLs currently in the database."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            rows = conn.execute("SELECT url FROM crawl_records").fetchall()
            conn.close()
            return [r[0] for r in rows]
        except sqlite3.OperationalError:
            return []
