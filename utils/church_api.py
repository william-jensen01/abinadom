"""
Church API access shared by the fetch scripts.

Sessions are created by the caller and passed in. Nothing here installs a
global cache: talk pages may come from the cache, but topic pages and the
named conference's contents page must always be fresh (FETCH_BUILD_SPEC.md,
"Caching rule").
"""

import os
from typing import Any, Dict

import requests
import requests_cache

API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
REQUEST_TIMEOUT = 30
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(ROOT_DIR, "http_cache")  # requests_cache adds .sqlite


def cached_session(cache_path: str = CACHE_PATH) -> requests.Session:
    """Session whose responses are cached on disk forever (talk pages)."""
    return requests_cache.CachedSession(
        cache_path, backend="sqlite", expire_after=requests_cache.NEVER_EXPIRE
    )


def fresh_session() -> requests.Session:
    """Plain, uncached session (topics, the named conference's contents page)."""
    return requests.Session()


def get_json(session: requests.Session, uri: str, retries: int = 1) -> Dict[str, Any]:
    """GET an API page by Church URI. Retries, then raises on failure."""
    url = f"{API_BASE_URL}{uri}"
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, ValueError):
            if attempt == retries:
                raise
