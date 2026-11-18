"""
Church API access shared by the fetch scripts.

Sessions are created by the caller and passed in. Nothing here installs a
global cache: talk pages may come from the cache, but topic pages and the
named conference's contents page must always be fresh, since they are what
change.

Politeness: requests are sequential, network requests start at least
MIN_INTERVAL seconds apart (cache hits aren't throttled), retries wait
RETRY_DELAY seconds, and sessions send a User-Agent naming the project.

Cache keys: the API answers with "Vary: Accept-Encoding", and requests_cache
honours it, so sessions pin Accept-Encoding. Otherwise the cache only works in
environments whose urllib3 offers the same encodings (a March cache built with
"gzip, deflate, zstd" was entirely missed by "gzip, deflate").
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
HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

_throttle_lock = threading.Lock()
_last_network_request = 0.0


def cached_session(cache_path: str | None = None) -> requests.Session:
    """Session whose responses are cached on disk forever (talk pages).

    The cache file is cache_path if given, else the path in the SCI_HTTP_CACHE
    environment variable (when set and non-empty), else CACHE_PATH.
    """
    if cache_path is None:
        cache_path = os.environ.get("SCI_HTTP_CACHE") or CACHE_PATH
    parent = os.path.dirname(os.path.abspath(cache_path))
    os.makedirs(parent, exist_ok=True)
    session = requests_cache.CachedSession(
        cache_path, backend="sqlite", expire_after=requests_cache.NEVER_EXPIRE
    )
    session.headers.update(HEADERS)
    return session


def fresh_session() -> requests.Session:
    """Plain, uncached session (topics, the named conference's contents page)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _get(session: requests.Session, url: str) -> requests.Response:
    """session.get, so network requests start at least MIN_INTERVAL apart."""
    global _last_network_request
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_network_request)
        if wait > 0:
            time.sleep(wait)
        started = time.monotonic()
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        if not getattr(response, "from_cache", False):
            _last_network_request = started
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


CONTENT_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content?lang=eng&uri="


def get_content(session: requests.Session, uri: str, retries: int = 1) -> requests.Response:
    """GET a page from the `type/content` endpoint (scripture pages), throttled like get_json.

    Returns the Response, so callers can store the body unmodified. Network errors and 5xx answers are
    retried; after the last try a network error is raised and a 5xx response is returned.
    """
    for attempt in range(retries + 1):
        try:
            response = _get(session, f"{CONTENT_URL}{uri}")
            if response.status_code < 500 or attempt == retries:
                return response
        except requests.exceptions.RequestException:
            if attempt == retries:
                raise
        time.sleep(RETRY_DELAY)
