"""Serves the local review pages and saves Garron's answers as he gives them.

A plain local server on this machine. Nothing leaves the computer, and every answer
is written to disk the moment it is given, so a review can be stopped and picked up
later. Two pages use it:
- the inch-confirmation page (`confirm-inch-values`), saving to data/inch-confirmations.csv
- the diagnosis review page (`review-diagnoses`, in diagnosis_review), saving to
  data/casebook.jsonl
"""

from __future__ import annotations

import json
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from vlm_eval import paths, review_items, review_page

# 8765 is commonly taken by other local tools, so start above the usual range.
PORT = 8790
RUNS = paths.ROOT / "runs"


class BaseHandler(BaseHTTPRequestHandler):
    """What every review page shares: quiet logging, replies, and drawing pictures."""

    def log_message(self, *args) -> None:
        """Stay quiet; the page is the interface, not the terminal."""

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, data) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except json.JSONDecodeError:
            return {}
        return body if isinstance(body, dict) else {}

    def _send_run_picture(self) -> None:
        """Crops and renders, served only from inside runs/."""
        target = (RUNS / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
        if target.is_file() and target.is_relative_to(RUNS.resolve()):
            self._send(200, target.read_bytes(), "image/png")
            return
        self._send(404, b"not found", "text/plain")


class Handler(BaseHandler):
    """The inch-confirmation page."""

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, review_page.build().encode(), "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            saved = {
                row["file"] + "|" + row["label"]: row
                for row in review_items.load_confirmations().values()
            }
            by_number = {}
            for item in review_page.build_items():
                row = saved.get(f"{item.file}|{item.label}")
                if row:
                    by_number[item.number] = row
            self._send_json(200, by_number)
            return
        self._send_run_picture()

    def do_POST(self) -> None:
        if self.path != "/api/answer":
            self._send(404, b"not found", "text/plain")
            return
        body = self._read_json()
        review_items.save_confirmation(
            {
                "file": body.get("file", ""),
                "label": body.get("label", ""),
                "axis": body.get("axis", ""),
                "recorded_mm": body.get("recorded_mm", ""),
                "confirmed_inch": body.get("confirmed_inch", ""),
                "confirmed_segments": "",
                "verdict": body.get("verdict", ""),
                "note": body.get("note", ""),
                "saved_at": self.date_time_string(),
            }
        )
        self._send(200, b'{"ok":true}', "application/json")


def _inch_page_stopped() -> str:
    return "Your answers are saved in data/inch-confirmations.csv"


def open_server(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    """A server for this page on the first free port from PORT, and its address."""
    port = PORT
    while True:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            port += 1
            if port > PORT + 40:
                raise
    return server, f"http://127.0.0.1:{port}/"


def serve(
    handler: type[BaseHTTPRequestHandler] = Handler,
    open_browser: bool = True,
    stopped: Callable[[], str] = _inch_page_stopped,
) -> None:
    """Serve one review page until Ctrl+C, then print what `stopped` says."""
    server, url = open_server(handler)
    print(f"Review page running at {url}", flush=True)
    print("Leave this running while you work. Press Ctrl+C when you're done.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopped. {stopped()}")
    finally:
        server.server_close()
