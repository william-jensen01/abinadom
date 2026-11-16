#!/usr/bin/env python3
"""Prepare one category of data per run. Never loads or verifies Weaviate; that is a separate step.

    setup_data.py talks [--version N|latest] [--base-url URL] [--force]
    setup_data.py scriptures

talks       fetch_sci.py --version <N>, then build.py --version <N>, then prints the .env line SCI_DB_VERSION=<N>.
            N is --version, `latest` (the newest release on the site, found as fetch_sci.py finds it) or, without
            --version, SCI_DB_VERSION (else 55). --force goes to build.py only, to overwrite an existing build; it
            does not download the release again (that is fetch_sci.py --force).
            After the build, warns when the build report lists SCI talks that have no Church data.
scriptures  fetch_scriptures.py, then build_scriptures.py.

Each step runs as its own script with this process's environment; a failed step stops the run with its exit code.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import fetch_sci  # noqa: E402


def step(script: str, *args) -> int:
    args = [str(a) for a in args]
    print(f"\n==> {' '.join([script, *args])}", flush=True)
    return subprocess.call([sys.executable, str(SCRIPTS / script), *args])


def stale_church_hint(n: int):
    """Warn when the build report lists SCI talks with no Church data. A missing or unreadable report says nothing."""
    db_dir = Path(os.environ.get("SCI_DB_DIR") or SCRIPTS.parent / "db")
    try:
        report = json.loads((db_dir / f"build_report.{n}.json").read_text())
        unexpected = report["sci_talks_without_church_data"]["unexpected"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    if not unexpected:
        return
    print(f"\nWarning: {len(unexpected)} SCI talks in release {n} are missing Church data "
          "(the Church JSON is older than this release). To fix it, refresh the Church JSON:")
    print("  in Docker:        git pull, then docker compose build tools")
    print("  on a dev machine: scripts/fetch.py --conference YYYY-MM, then commit the JSON")
    print(f"then rebuild: setup_data.py talks --version {n} --force")


def talks(args) -> int:
    try:
        n = fetch_sci.resolve_version(args.version, args.base_url, fetch_sci.sci_dir())
    except fetch_sci.FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    code = step("fetch_sci.py", "--version", n, "--base-url", args.base_url)
    if code:
        return code
    code = step("build.py", "--version", n, *(["--force"] if args.force else []))
    if code:
        return code
    stale_church_hint(n)
    print(f"\nSet this in .env:\nSCI_DB_VERSION={n}")
    return 0


def scriptures(_args) -> int:
    for script in ("fetch_scriptures.py", "build_scriptures.py"):
        code = step(script)
        if code:
            return code
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare one category of data per run (never loads Weaviate).")
    sub = ap.add_subparsers(dest="category", required=True)
    t = sub.add_parser("talks", help="fetch an SCI release and build the talk dbs from it")
    t.add_argument("--version", type=fetch_sci.version_arg,
                   help="release number, or 'latest' to find the newest (default: SCI_DB_VERSION, else 55)")
    t.add_argument("--base-url", default=fetch_sci.DEFAULT_BASE_URL,
                   help=f"release site (default {fetch_sci.DEFAULT_BASE_URL})")
    t.add_argument("--force", action="store_true", help="overwrite an existing build (does not re-download)")
    t.set_defaults(run=talks)
    sub.add_parser("scriptures", help="fetch the scriptures and build scripture.db").set_defaults(run=scriptures)
    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
