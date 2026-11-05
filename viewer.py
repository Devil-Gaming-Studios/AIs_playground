"""Tiny read-only web viewer for Round Table runs: python viewer.py [--port 8000]"""
import argparse
import html
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

RUNS = Path("runs")
MAX_BYTES = 1_000_000  # largest file we will show
MAX_ENTRIES = 500  # largest directory listing we will show
SLOTS = threading.BoundedSemaphore(16)  # max concurrent requests
STYLE = (
    "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
    "pre{background:#f4f4f4;padding:1rem;overflow:auto;white-space:pre-wrap}a{color:#0b5fff}</style>"
)


def page(title: str, body: str) -> bytes:
    return f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>{STYLE}{body}".encode()


def safe_path(*parts: str) -> Path | None:
    root = RUNS.resolve()
    current = root
    for part in parts:  # refuse symlinks anywhere along the path
        current = current / part
        if current.is_symlink():
            return None
    target = current.resolve()
    return target if target == root or root in target.parents else None


def read_text_limited(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))  # no symlink at open time
    with os.fdopen(fd, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    note = "\n\n[truncated]" if len(data) > MAX_BYTES else ""
    return data[:MAX_BYTES].decode("utf-8", errors="replace") + note


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not SLOTS.acquire(blocking=False):
            return self.send(503, page("Busy", "<h1>Busy, try again</h1>"))
        try:
            self.handle_get()
        finally:
            SLOTS.release()

    def handle_get(self) -> None:
        parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
        target = safe_path(*parts)
        if target is None or not target.exists():
            return self.send(404, page("Not found", "<h1>Not found</h1><a href='/'>Back</a>"))
        if target.is_dir():
            items = sorted(target.iterdir(), reverse=(target == RUNS.resolve()))
            more = "<li>[listing truncated]</li>" if len(items) > MAX_ENTRIES else ""
            links = "".join(
                f"<li><a href='{html.escape(quote('/' + '/'.join([*parts, p.name])))}'>{html.escape(p.name)}"
                f"{'/' if p.is_dir() else ''}</a></li>"
                for p in items[:MAX_ENTRIES]
            ) + more
            return self.send(200, page("Runs", f"<h1>/{html.escape('/'.join(parts))}</h1><ul>{links}</ul>"))
        text = read_text_limited(target)
        self.send(200, page(target.name, f"<a href='/'>Home</a><h1>{html.escape(target.name)}</h1><pre>{html.escape(text)}</pre>"))

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="View Round Table runs in a browser.")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    RUNS.mkdir(exist_ok=True)
    print(f"Viewing runs at http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
