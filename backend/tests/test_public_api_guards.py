"""The API is reachable by anyone on the internet, so the guards are part of it.

Two risks, two mechanisms: maintenance endpoints spend a sponsor's quota with
our key and need an operator secret; task endpoints spend third parties'
capacity and need a per-caller ceiling that a judge never notices.
"""

import pytest
from fastapi import HTTPException, Request

import guards


def test_operator_gate_fails_closed_when_unconfigured(monkeypatch):
    """No secret configured must mean unreachable, not open."""
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    with pytest.raises(HTTPException) as caught:
        guards.require_operator(x_admin_token="anything")

    assert caught.value.status_code == 503


def test_operator_gate_rejects_a_missing_or_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")

    for supplied in (None, "", "wrong"):
        with pytest.raises(HTTPException) as caught:
            guards.require_operator(x_admin_token=supplied)
        assert caught.value.status_code == 401


def test_operator_gate_accepts_the_configured_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")

    assert guards.require_operator(x_admin_token="correct-horse") is None


def test_rate_limiter_allows_up_to_the_limit_then_refuses():
    limiter = guards.RateLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        limiter.check("1.2.3.4")

    with pytest.raises(HTTPException) as caught:
        limiter.check("1.2.3.4")
    assert caught.value.status_code == 429
    assert "Retry-After" in caught.value.headers


def test_rate_limiter_meters_each_caller_separately():
    """One noisy caller must not lock a judge out."""
    limiter = guards.RateLimiter(limit=2, window_seconds=60)

    limiter.check("1.1.1.1")
    limiter.check("1.1.1.1")
    limiter.check("2.2.2.2")  # unaffected by the first caller's spend


def test_rate_limiter_forgets_hits_once_the_window_passes(monkeypatch):
    limiter = guards.RateLimiter(limit=1, window_seconds=60)
    clock = [1000.0]
    monkeypatch.setattr(guards.time, "monotonic", lambda: clock[0])

    limiter.check("1.2.3.4")
    clock[0] += 61
    limiter.check("1.2.3.4")  # window has rolled; allowed again


def _request(headers: dict, client_host: str | None = "10.0.0.1"):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_caller_is_identified_by_the_cloudflare_header():
    """Behind the tunnel every socket looks the same, so the limit must key on
    the header Cloudflare sets rather than the peer address."""
    assert guards.client_key(_request({"CF-Connecting-IP": "203.0.113.9"})) == "203.0.113.9"


def test_caller_falls_back_to_the_socket_for_direct_connections():
    assert guards.client_key(_request({})) == "10.0.0.1"


# --- endpoint verdicts must not be allowed to go stale -----------------------

def test_stale_verdicts_are_selected_for_reprobing(monkeypatch):
    """A verdict is a claim about the past. The selector must pick up anything
    unprobed, anything never stamped, and anything older than the TTL — or the
    hireable pool can only shrink between now and judging."""
    import server
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=server.ENDPOINT_VERDICT_TTL_HOURS)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(hours=server.ENDPOINT_VERDICT_TTL_HOURS + 1)).isoformat()

    def selected(doc):
        clauses = [
            "endpoint_status" not in doc,
            doc.get("endpoint_checked_at") is not None and doc["endpoint_checked_at"] < cutoff,
            "endpoint_checked_at" not in doc,
        ]
        return any(clauses)

    assert selected({}) is True                                            # never probed
    assert selected({"endpoint_status": "live"}) is True                   # probed before stamps existed
    assert selected({"endpoint_status": "live", "endpoint_checked_at": old}) is True
    assert selected({"endpoint_status": "live", "endpoint_checked_at": fresh}) is False


def test_reprobe_ttl_is_shorter_than_a_judging_window():
    """Whatever the value, it must be short enough that a dead endpoint is not
    still advertised days later."""
    import server

    assert 1 <= server.ENDPOINT_VERDICT_TTL_HOURS <= 24


# --- an icon URL is attacker-controlled, so the limit must bound reading ------

@pytest.fixture
def anyio_backend():
    return "asyncio"


class _StreamingResponse:
    """Mimics httpx's streaming response over a body delivered in chunks."""

    def __init__(self, chunks, status=200, content_type="image/png", declared=None):
        self.status_code = status
        self.headers = {"content-type": content_type}
        if declared is not None:
            self.headers["content-length"] = str(declared)
        self._chunks = chunks
        self.read_bytes = 0

    async def aiter_bytes(self):
        for chunk in self._chunks:
            self.read_bytes += len(chunk)
            yield chunk


def _client_streaming(response):
    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *_):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def stream(self, *_a, **_kw):
            return _Ctx()

    return lambda **_kw: _Client()


@pytest.mark.anyio
async def test_an_endless_body_is_abandoned_at_the_limit(monkeypatch):
    """The finding this exists to close: measuring the body after reading it let
    a hostile host buffer gigabytes against a one-megabyte cap."""
    import icon_proxy

    endless = _StreamingResponse([b"x" * 100_000] * 1000)
    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", _client_streaming(endless))

    assert await icon_proxy._fetch_icon("https://host.example/i.png") is None
    # Stopped shortly past the cap rather than reading the whole 100MB.
    assert endless.read_bytes <= icon_proxy.MAX_ICON_BYTES + 100_000


@pytest.mark.anyio
async def test_an_oversized_content_length_is_refused_without_reading(monkeypatch):
    import icon_proxy

    lying = _StreamingResponse([b"x" * 10], declared=icon_proxy.MAX_ICON_BYTES + 1)
    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", _client_streaming(lying))

    assert await icon_proxy._fetch_icon("https://host.example/i.png") is None
    assert lying.read_bytes == 0


@pytest.mark.anyio
async def test_a_normal_icon_is_returned(monkeypatch):
    import icon_proxy

    ok = _StreamingResponse([b"\x89PNG", b"data"])
    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", _client_streaming(ok))

    assert await icon_proxy._fetch_icon("https://host.example/i.png") == (b"\x89PNGdata", "image/png")


@pytest.mark.anyio
async def test_a_disallowed_content_type_is_refused_without_reading(monkeypatch):
    import icon_proxy

    html = _StreamingResponse([b"<html>"], content_type="text/html")
    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", _client_streaming(html))

    assert await icon_proxy._fetch_icon("https://host.example/i.png") is None
    assert html.read_bytes == 0
