from typing import Mapping, Optional
from urllib.parse import urlparse

CONTENT_HTML = "html"
CONTENT_PDF = "pdf"
CONTENT_DOCX = "docx"
CONTENT_OTHER = "other"


def detect_content_type(url: str, headers: Optional[Mapping[str, str]] = None) -> str:
    content_type = ""
    if headers:
        content_type = headers.get("Content-Type", "")
    content_type = content_type.lower()

    path = urlparse(url).path.lower()
    if "application/pdf" in content_type or path.endswith(".pdf"):
        return CONTENT_PDF
    if (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        in content_type
        or path.endswith(".docx")
    ):
        return CONTENT_DOCX
    if (
        "text/html" in content_type
        or content_type.startswith("text/")
        or path.endswith("/")
        or path.endswith(".html")
        or path.endswith(".htm")
    ):
        return CONTENT_HTML
    return CONTENT_OTHER
