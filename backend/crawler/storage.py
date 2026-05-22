import json
import os
import sqlite3
from typing import Optional, Tuple

from .models import CrawlRecord


class CrawlStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    status_code INTEGER,
                    content_type TEXT,
                    content_hash TEXT,
                    title TEXT,
                    text TEXT,
                    discovered_urls TEXT,
                    etag TEXT,
                    last_modified TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_crawl_records_url ON crawl_records(url)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    status_code INTEGER,
                    content_hash TEXT,
                    etag TEXT,
                    unchanged INTEGER NOT NULL
                )
                """
            )

    def save_record(self, record: CrawlRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO crawl_records (
                    url,
                    fetched_at,
                    status_code,
                    content_type,
                    content_hash,
                    title,
                    text,
                    discovered_urls,
                    etag,
                    last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.url,
                    record.fetched_at.isoformat(),
                    record.status_code,
                    record.content_type,
                    record.content_hash,
                    record.title,
                    record.text,
                    json.dumps(record.discovered_urls),
                    record.etag,
                    record.last_modified,
                ),
            )

    def save_history(self, record: CrawlRecord, unchanged: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO crawl_history (
                    url,
                    fetched_at,
                    status_code,
                    content_hash,
                    etag,
                    unchanged
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.url,
                    record.fetched_at.isoformat(),
                    record.status_code,
                    record.content_hash,
                    record.etag,
                    1 if unchanged else 0,
                ),
            )

    def get_latest_fingerprint(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT content_hash, etag
                FROM crawl_records
                WHERE url = ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (url,),
            )
            row = cursor.fetchone()
            if not row:
                return None, None
            return row[0], row[1]
