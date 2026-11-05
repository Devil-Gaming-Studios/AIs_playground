"""Tiny read-only web viewer for Round Table runs: python viewer.py [--port 8000]"""
import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

RUNS = Path("runs")
STYLE = (
    "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
    "pre{background:#f4f4f4;padding:1rem;overflow:auto;white-space:pre-wrap}a{color:#0b5fff}</style>"
)


def page(title: str, body: str) -> bytes:
    return f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>{STYLE}{body}".encode()


def safe_path(*parts: str) -> Path | None:
    root = RUNS.resolve()
    target = root.joinpath(*parts).resolve()
    return target if target == root or root in target.parents else None


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
        target = safe_path(*parts)
        if target is None or not target.exists():
            return self.send(404, page("Not found", "<h1>Not found</h1><a href='/'>Back</a>"))
        if target.is_dir():
            items = sorted(target.iterdir(), reverse=(target == RUNS.resolve()))
            links = "".join(
                f"<li><a href='{html.escape('/'.join(['', *parts, p.name]))}'>{html.escape(p.name)}"
                f"{'/' if p.is_dir() else ''}</a></li>"
                for p in items
            )
            return self.send(200, page("Runs", f"<h1>/{html.escape('/'.join(parts))}</h1><ul>{links}</ul>"))
        text = target.read_text(encoding="utf-8", errors="replace")
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
