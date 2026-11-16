"""A local stand-in for the BYU SCI release site (https://scriptures.byu.edu/sci.<N>.zip), for the fetch tests.

The fake zips copy the real sci.55.zip's layout: core.<N>.db and content.<N>.db at
the top level, plus a `lucene/` directory entry and files under it. The two .db members are not real SQLite files:
they are the 16-byte SQLite header plus random bytes, enough for a header check, so nothing here opens a database.
"""
import hashlib
import io
import os
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SQLITE_MAGIC = b"SQLite format 3\x00"   # the SQLite file format's 16-byte header string
LUCENE_FILES = ("segments", "_1xkb.fnm", "_1xkb.prx", "_1xkb.tis")   # names from the real sci.55.zip lucene/ (a subset)


def fake_db(tag: str, size: int = 4096) -> bytes:
    body = hashlib.sha256(tag.encode()).digest() * (size // 32 + 1)
    return SQLITE_MAGIC + body[: size - len(SQLITE_MAGIC)]


def release_members(n, tag=""):
    """{zip member name: bytes} for a well-formed release N (`tag` makes a different build of the same N)."""
    m = {f"core.{n}.db": fake_db(f"core{n}{tag}"), f"content.{n}.db": fake_db(f"content{n}{tag}")}
    for f in LUCENE_FILES:
        m[f"lucene/{f}"] = hashlib.sha256(f"{n}{tag}{f}".encode()).digest() * 8
    return m


def make_zip(members, dirs=("lucene/",), symlinks=()):
    """members: {name: bytes}. dirs: directory entries to add first. symlinks: {name: target} as symlink entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in dirs:
            zi = zipfile.ZipInfo(d)
            zi.external_attr = (0o40775 << 16) | 0x10
            z.writestr(zi, b"")
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = 0o100664 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
        for name, target in dict(symlinks).items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = 0o120777 << 16
            z.writestr(zi, target)
    return buf.getvalue()


def release_zip(n, tag=""):
    return make_zip(release_members(n, tag))


class SciServer:
    """releases: {N: zip bytes}. errors: {N: http status} answered for that version instead (e.g. 500).
    truncate: set of N whose GET body is cut in half after a full Content-Length is announced.
    Every request is logged as (method, path, status)."""

    def __init__(self, releases=None, errors=None, truncate=()):
        self.releases = dict(releases or {})
        self.etags = {n: f'"{hashlib.sha256(b).hexdigest()[:16]}"' for n, b in self.releases.items()}
        self.errors = dict(errors or {})
        self.truncate = set(truncate)
        self.log = []
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _version(self):
                p = self.path.split("?")[0]
                name = p.rsplit("/", 1)[-1]
                if p == "/" + name and name.startswith("sci.") and name.endswith(".zip"):
                    v = name[4:-4]
                    if v.isdigit():
                        return int(v)
                return None

            def _send(self, status, headers=(), body=b"", cut=False):
                outer.log.append((self.command, self.path, status))
                self.send_response(status)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                if cut:
                    self.send_header("Connection", "close")
                self.end_headers()
                if self.command == "GET" and body:
                    self.wfile.write(body[: len(body) // 2] if cut else body)
                    if cut:
                        self.wfile.flush()
                        self.close_connection = True

            def _handle(self):
                n = self._version()
                if n is not None and n in outer.errors:
                    return self._send(outer.errors[n], [("Content-Type", "text/html")], b"<h1>error</h1>")
                if n is None or n not in outer.releases:
                    return self._send(404, [("Content-Type", "text/html")], b"<h1>Not Found</h1>")
                etag = outer.etags[n]
                if self.headers.get("If-None-Match") == etag:
                    return self._send(304, [("ETag", etag)])
                body = outer.releases[n]
                self._send(200, [("Content-Type", "application/zip"), ("ETag", etag),
                                 ("Last-Modified", "Tue, 27 Oct 2026 03:40:10 GMT")], body, cut=n in outer.truncate)

            do_GET = _handle
            do_HEAD = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def replace(self, n, data):
        """Publish a new build of release N (new bytes, new ETag)."""
        self.releases[n] = data
        self.etags[n] = f'"{hashlib.sha256(data).hexdigest()[:16]}"'

    def zip_downloads(self, n=None):
        """Full 200 GETs of a zip (of release N, if given)."""
        return [p for m, p, s in self.log if m == "GET" and s == 200 and (n is None or p.endswith(f"/sci.{n}.zip"))]

    def versions_asked(self):
        out = set()
        for _m, p, _s in self.log:
            name = p.split("?")[0].rsplit("/", 1)[-1]
            if name.startswith("sci.") and name.endswith(".zip") and name[4:-4].isdigit():
                out.add(int(name[4:-4]))
        return out

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


def closed_port_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def tree_files(d):
    """{relative path: bytes} for every file under d (directories implied)."""
    out = {}
    for root, _dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, d)] = open(p, "rb").read()
    return out
