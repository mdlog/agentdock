"""Guards for an API that anyone on the internet can call.

Two distinct risks, so two distinct mechanisms. The maintenance endpoints spend
a sponsor's rate-limited quota with our key, so they need an operator secret and
nothing less. The task endpoints spend third-party agents' capacity and our own
outbound bandwidth, so they need a ceiling per caller rather than a password —
a judge must be able to hire an agent without being handed a token.
"""

import hmac
import os
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request


def require_operator(x_admin_token: str | None = Header(default=None)) -> None:
    """Gate maintenance endpoints on a shared secret.

    Fails closed: with no ADMIN_TOKEN configured the endpoints are unreachable
    rather than open, because the failure that matters is a stranger triggering
    a 256k-agent sync against the sponsor API we authenticate to with our key.
    """
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Maintenance endpoints are disabled: ADMIN_TOKEN is not configured")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Operator token required")


class RateLimiter:
    """Fixed-window-free sliding counter, per key, in memory.

    In memory on purpose: one process serves this deployment, and a limiter that
    needs its own datastore is a second thing that can fail during judging. The
    deque holds only timestamps inside the window, so memory is bounded by
    (callers seen recently x limit).
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = int(self.window - (now - hits[0])) + 1
            raise HTTPException(429, f"Too many requests. Try again in {retry_after}s.",
                                headers={"Retry-After": str(retry_after)})
        hits.append(now)
        # Callers that fall silent should not be remembered forever.
        if len(self._hits) > 4096:
            for stale, times in list(self._hits.items()):
                if not times or now - times[-1] > self.window:
                    del self._hits[stale]


def client_key(request: Request) -> str:
    """Identify the caller behind the tunnel.

    Cloudflare terminates the connection, so request.client is always the tunnel;
    CF-Connecting-IP carries the real caller and cannot be spoofed by the client
    because Cloudflare overwrites it. The direct-connection fallback exists for
    local runs, where the socket address is the truth.
    """
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"


# Hiring an agent makes us call a third party, so it is metered more tightly
# than reading the catalogue. Both ceilings sit far above what a judge exploring
# the marketplace would ever reach.
task_limiter = RateLimiter(limit=int(os.environ.get("RATE_LIMIT_TASKS", "20")), window_seconds=60)
run_limiter = RateLimiter(limit=int(os.environ.get("RATE_LIMIT_RUNS", "30")), window_seconds=60)
