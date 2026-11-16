#!/usr/bin/env python3
"""Download and install a BYU Scripture Citation Index (SCI) release.

    fetch_sci.py [--version N|latest] [--base-url URL] [--force]

Fetches <base>/sci.<N>.zip (base https://scriptures.byu.edu) and installs it in $SCI_DB_DIR/sci (the
checkout's db/sci when SCI_DB_DIR is unset or empty):

    core.<N>.db   content.<N>.db   lucene.<N>/ (the zip's lucene/, kept but unused)   sci.<N>.json (download record)

Anything else in the zip is ignored, and other releases in sci/ are never touched.

--version defaults to SCI_DB_VERSION (else 55). `latest` starts at the higher of that and the newest
core.<N>.db already in sci/, then tries the next three numbers after the newest release found so far: a hit
becomes the newest, three misses in a row end the search. Only a 404 is a miss; any other answer or a network
error stops the run.

An installed release with a record is downloaded again only if the site's ETag changed; one placed by hand
(no record) is kept. --force downloads it regardless.

The zip is downloaded and unpacked beside sci/, refused whole if an entry is absolute, climbs out with `..`
or is a symlink, and each .db must start with the SQLite header (no database is opened). Only then are the
files moved into place. A failed or interrupted run leaves sci/ as it was. Standard library only.
"""
import argparse
import http.client
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_BASE_URL = "https://scriptures.byu.edu"
DEFAULT_VERSION = 55
MISSES_TO_STOP = 3
TIMEOUT = 60
USER_AGENT = "lds-sci-mcp-fetch/1.0 (SCI release sync)"
SQLITE_HEADER = b"SQLite format 3\x00"
NET_ERRORS = (OSError, http.client.HTTPException)   # urllib's URLError is an OSError


class FetchError(Exception):
    pass


def sci_dir() -> Path:
    base = os.environ.get("SCI_DB_DIR")
    return (Path(base) if base else Path(__file__).resolve().parent.parent / "db") / "sci"


def env_version() -> int:
    raw = os.environ.get("SCI_DB_VERSION")
    if not raw:
        return DEFAULT_VERSION
    if not raw.isdigit():
        raise FetchError(f"SCI_DB_VERSION must be a release number, got {raw!r}")
    return int(raw)


def zip_url(base: str, n: int) -> str:
    return f"{base.rstrip('/')}/sci.{n}.zip"


def open_url(url: str, method: str = "GET", headers=None):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def on_site(base: str, n: int) -> bool:
    url = zip_url(base, n)
    try:
        with open_url(url, "HEAD"):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise FetchError(f"{url} answered {e.code}")
    except NET_ERRORS as e:
        raise FetchError(f"could not reach {url}: {e}")


def find_latest(base: str, sci: Path) -> int:
    local = [int(m.group(1)) for p in sci.glob("core.*.db") if (m := re.fullmatch(r"core\.(\d+)\.db", p.name))]
    newest = max([env_version(), *local])
    n, misses = newest, 0
    while misses < MISSES_TO_STOP:
        n += 1
        if on_site(base, n):
            newest, misses = n, 0
        else:
            misses += 1
    print(f"Latest release: {newest}")
    return newest


def resolve_version(version, base: str, sci: Path) -> int:
    """The release number to fetch: `version` as given (an int or "latest"), or SCI_DB_VERSION when None."""
    if version is None:
        return env_version()
    if version == "latest":
        return find_latest(base, sci)
    return version


def download(url: str, dest: Path, etag=None):
    """Save url to dest and return the response headers, or None when the site says the ETag is unchanged."""
    try:
        resp = open_url(url, headers={"If-None-Match": etag} if etag else None)
    except urllib.error.HTTPError as e:
        if e.code == 304 and etag:
            return None
        if e.code == 404:
            raise FetchError(f"{url} not found (404): there is no such release")
        raise FetchError(f"{url} answered {e.code}")
    except NET_ERRORS as e:
        raise FetchError(f"could not reach {url}: {e}")
    print(f"Downloading {url}", flush=True)
    try:
        with resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
    except NET_ERRORS as e:
        raise FetchError(f"download of {url} failed: {e}")
    expected = resp.headers.get("Content-Length")
    if expected is not None and dest.stat().st_size != int(expected):
        raise FetchError(f"download of {url} was cut short: {dest.stat().st_size} of {expected} bytes")
    return resp.headers


def unsafe(info: zipfile.ZipInfo):
    name = info.filename.replace("\\", "/")
    if name.startswith("/") or re.match(r"[A-Za-z]:", name):
        return "is an absolute path"
    if ".." in name.split("/"):
        return "climbs out with '..'"
    if stat.S_ISLNK(info.external_attr >> 16):
        return "is a symlink"
    return None


def unpack(zip_path: Path, n: int, stage: Path):
    """Check the zip, then write core.<n>.db, content.<n>.db and lucene.<n>/ into stage."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise FetchError(f"sci.{n}.zip is not a valid zip: {e}")
    with zf:
        for info in zf.infolist():
            why = unsafe(info)
            if why:
                raise FetchError(f"refusing sci.{n}.zip: entry {info.filename!r} {why}")
        dbs = [f"core.{n}.db", f"content.{n}.db"]
        missing = [db for db in dbs if db not in zf.namelist()]
        if missing:
            raise FetchError(f"sci.{n}.zip has no {', '.join(missing)}")
        bad = zf.testzip()
        if bad:
            raise FetchError(f"sci.{n}.zip is corrupt at {bad!r}")
        for db in dbs:
            with zf.open(db) as src:
                if src.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                    raise FetchError(f"{db} in sci.{n}.zip is not an SQLite database")
        lucene = stage / f"lucene.{n}"
        lucene.mkdir()
        for info in zf.infolist():
            if info.filename in dbs:
                target = stage / info.filename
            elif info.filename.startswith("lucene/") and not info.is_dir():
                target = lucene / info.filename[len("lucene/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                continue
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def install(stage: Path, sci: Path, n: int, backup: Path):
    """Move the staged release into sci/. If anything fails or is interrupted, put sci/ back as it was."""
    names = [f"core.{n}.db", f"content.{n}.db", f"lucene.{n}", f"sci.{n}.json"]
    sci.mkdir(exist_ok=True)
    backup.mkdir()
    moved_aside, placed = [], []
    try:
        for name in names:
            if os.path.lexists(sci / name):
                os.rename(sci / name, backup / name)
                moved_aside.append(name)
        for name in names:
            os.rename(stage / name, sci / name)
            placed.append(name)
    except BaseException as e:
        for name in placed:
            p = sci / name
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        for name in moved_aside:
            os.rename(backup / name, sci / name)
        if isinstance(e, OSError):
            raise FetchError(f"could not install release {n} in {sci}: {e}")
        raise


def fetch_release(base: str, sci: Path, n: int, force: bool):
    record_path = sci / f"sci.{n}.json"
    etag = None
    if not force and (sci / f"core.{n}.db").exists() and (sci / f"content.{n}.db").exists():
        if not record_path.exists():
            print(f"Release {n} is already in {sci} (placed by hand, no download record); keeping it.")
            return
        try:
            etag = json.loads(record_path.read_text()).get("etag")
        except (OSError, ValueError, AttributeError):
            etag = None   # an unreadable record: download again
    url = zip_url(base, n)
    sci.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".sci-fetch-{n}-", dir=sci.parent))
    try:
        zip_path = work / f"sci.{n}.zip"
        headers = download(url, zip_path, etag)
        if headers is None:
            print(f"Release {n} is unchanged on the site (same ETag); nothing downloaded.")
            return
        stage = work / "stage"
        stage.mkdir()
        unpack(zip_path, n, stage)
        (stage / f"sci.{n}.json").write_text(json.dumps({
            "version": n,
            "url": url,
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
            "size": zip_path.stat().st_size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2) + "\n")
        install(stage, sci, n, work / "old")
        print(f"Installed release {n} in {sci}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def version_arg(text: str):
    if text == "latest":
        return text
    if not text.isdigit():
        raise argparse.ArgumentTypeError("must be a release number or 'latest'")
    return int(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download and install an SCI release into $SCI_DB_DIR/sci.")
    ap.add_argument("--version", type=version_arg,
                    help="release number, or 'latest' to find the newest (default: SCI_DB_VERSION, else 55)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"release site (default {DEFAULT_BASE_URL})")
    ap.add_argument("--force", action="store_true", help="download again even if the release is installed")
    args = ap.parse_args(argv)
    sci = sci_dir()
    try:
        n = resolve_version(args.version, args.base_url, sci)
        fetch_release(args.base_url, sci, n, args.force)
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
