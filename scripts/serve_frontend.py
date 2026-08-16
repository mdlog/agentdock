#!/usr/bin/env python3
"""Serve the built frontend, with the two behaviours a single-page app needs.

Routing: React Router owns the URL space, so any path that is not a real file
must answer with index.html rather than 404. Without it, a judge who reloads on
/hire/<id> or follows a shared link gets nothing.

Caching: the dev server published one stable filename (bundle.js) behind
Cloudflare's four-hour cache, so a returning visitor could be served yesterday's
app while the origin had today's. Production filenames carry a content hash,
which makes them safe to cache forever — and makes index.html, the file that
names them, the one thing that must never be cached.

Stdlib only, on purpose: this sits behind Cloudflare serving four static files,
and a deploy that cannot break because a dependency moved is worth more here
than features nothing uses.
"""

import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "build").resolve()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "3100"))

# Everything under /static/ is content-hashed by the build, so a name never
# refers to two different files.
IMMUTABLE_PREFIX = "/static/"


class SPAHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _route_to_app(self) -> None:
        """Point a client-side route at index.html; leave real files alone."""
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in ("", "/"):
            self.path = "/index.html"
            return
        candidate = (ROOT / path.lstrip("/")).resolve()
        # The containment check matters even though translate_path sanitises:
        # this decides what to *serve*, so it must not be reachable outside root.
        outside = ROOT != candidate and ROOT not in candidate.parents
        if outside or not candidate.is_file():
            self.path = "/index.html"

    def do_GET(self):  # noqa: N802 - stdlib naming
        self._route_to_app()
        super().do_GET()

    def do_HEAD(self):  # noqa: N802 - stdlib naming
        self._route_to_app()
        super().do_HEAD()

    def end_headers(self):
        if self.path.startswith(IMMUTABLE_PREFIX):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        # One line per request, no client address: journald already timestamps,
        # and the address is always the tunnel.
        sys.stdout.write(f"{fmt % args}\n")
        sys.stdout.flush()


def main() -> int:
    index = ROOT / "index.html"
    if not index.is_file():
        sys.stderr.write(f"No build at {ROOT} (expected {index}). Run: npm run build\n")
        return 1
    server = ThreadingHTTPServer((HOST, PORT), SPAHandler)
    print(f"AgentDock frontend: {ROOT} on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
