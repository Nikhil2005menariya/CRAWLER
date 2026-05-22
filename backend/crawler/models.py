from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CrawlRecord:
    url: str
    fetched_at: datetime
    status_code: int
    content_type: str
    content_hash: str
    text: str
    title: Optional[str] = None
    discovered_urls: List[str] = field(default_factory=list)
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
