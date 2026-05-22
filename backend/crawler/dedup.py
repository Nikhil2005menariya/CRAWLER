from typing import Optional

import xxhash


def compute_content_hash(text: str) -> str:
    return xxhash.xxh64(text.encode("utf-8")).hexdigest()


def is_unchanged(
    previous_hash: Optional[str],
    previous_etag: Optional[str],
    new_hash: str,
    new_etag: Optional[str],
) -> bool:
    if new_etag and previous_etag and new_etag == previous_etag:
        return True
    if previous_hash and new_hash == previous_hash:
        return True
    return False
