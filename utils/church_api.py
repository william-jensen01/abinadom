"""
Church API access shared by the fetch scripts.

Sessions are created by the caller and passed in. Nothing here installs a
global cache: talk pages may come from the cache, but topic pages and the
named conference's contents page must always be fresh (FETCH_BUILD_SPEC.md,
"Caching rule").

Politeness: requests are sequential, at most one network request every
MIN_INTERVAL seconds (cache hits aren't throttled), retries wait RETRY_DELAY
seconds, and sessions send a User-Agent naming the project.
"""

import os
import threading
import time
from typing import Any, Dict

import requests
import requests_cache

API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
REQUEST_TIMEOUT = (5, 30)  # (connect, read): a dead address (e.g. broken IPv6) costs 5s, not 30s
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(ROOT_DIR, "http_cache")  # requests_cache adds .sqlite
MIN_INTERVAL = 0.5  # seconds between network requests (≤ 2/s)
RETRY_DELAY = 5.0  # seconds before retrying a failed request
USER_AGENT = "lds-sci-mcp-fetch/1.0 (conference metadata sync; sequential, max 2 req/s)"

_throttle_lock = threading.Lock()
_last_network_request = 0.0


def cached_session(cache_path: str = CACHE_PATH) -> requests.Session:
    """Session whose responses are cached on disk forever (talk pages)."""
    session = requests_cache.CachedSession(
        cache_path, backend="sqlite", expire_after=requests_cache.NEVER_EXPIRE
    )
    session.headers["User-Agent"] = USER_AGENT
    return session


def fresh_session() -> requests.Session:
    """Plain, uncached session (topics, the named conference's contents page)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get(session: requests.Session, url: str) -> requests.Response:
    """session.get, spaced so network requests are at least MIN_INTERVAL apart."""
    global _last_network_request
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_network_request)
        if wait > 0:
            time.sleep(wait)
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        if not getattr(response, "from_cache", False):
            _last_network_request = time.monotonic()
        return response


def get_json(session: requests.Session, uri: str, retries: int = 1) -> Dict[str, Any]:
    """GET an API page by Church URI. Retries, then raises on failure."""
    url = f"{API_BASE_URL}{uri}"
    for attempt in range(retries + 1):
        try:
            response = _get(session, url)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(RETRY_DELAY)
