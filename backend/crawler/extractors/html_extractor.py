from typing import List, Tuple
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup


def extract_html(html: str, base_url: str) -> Tuple[str, List[str], str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None

    discovered: List[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if href.startswith(("mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        absolute, _ = urldefrag(absolute)
        if absolute:
            discovered.append(absolute)

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_text = "\n".join(lines)

    return cleaned_text, _dedupe_urls(discovered), title


def _dedupe_urls(urls: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered
