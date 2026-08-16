"""Onchain icon proxy tests: security validation, fallback behavior, and cache semantics."""

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

import icon_proxy
from icon_proxy import _public_https_url, get_agent_icon


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture(scope="session")
def api_base_url() -> str:
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _pick_agent(items: list[dict], *, has_source_icon: bool) -> dict | None:
    for row in items:
        if bool(row.get("has_source_icon")) is has_source_icon:
            return row
    return None


# Public icon route and privacy module tests
def test_mainnet_source_icon_route_returns_image_bytes(api_client: requests.Session, api_base_url: str):
    agents = api_client.get(
        f"{api_base_url}/api/onchain/agents", params={"network": "mainnet"}, timeout=40
    )
    assert agents.status_code == 200
    source_agent = _pick_agent(agents.json()["items"], has_source_icon=True)
    if not source_agent:
        pytest.skip("No source-icon agent available in synced mainnet sample")

    token_id = source_agent["token_id"]
    icon = api_client.get(f"{api_base_url}/api/onchain/agents/mainnet/{token_id}/icon", timeout=40)
    assert icon.status_code == 200
    content_type = icon.headers.get("content-type", "")
    assert content_type.startswith("image/")
    assert icon.headers.get("X-Agent-Icon-Source") == "8004scan"
    assert len(icon.content) > 0


def test_icon_route_invalid_network_returns_400(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents/invalid/1/icon", timeout=30)
    assert response.status_code == 400
    assert "network must be mainnet or testnet" in response.json()["detail"]


def test_no_source_icon_agent_gets_svg_fallback(api_client: requests.Session, api_base_url: str):
    agents = api_client.get(
        f"{api_base_url}/api/onchain/agents", params={"network": "mainnet"}, timeout=40
    )
    assert agents.status_code == 200
    fallback_agent = _pick_agent(agents.json()["items"], has_source_icon=False)
    if not fallback_agent:
        pytest.skip("No fallback-icon agent available in synced mainnet sample")

    token_id = fallback_agent["token_id"]
    icon = api_client.get(f"{api_base_url}/api/onchain/agents/mainnet/{token_id}/icon", timeout=40)
    assert icon.status_code == 200
    assert icon.headers.get("content-type", "").startswith("image/svg+xml")
    assert icon.headers.get("X-Agent-Icon-Source") == "generated-fallback"
    assert icon.content.startswith(b"<svg")


def test_public_agent_responses_hide_raw_source_url_and_api_key(api_client: requests.Session, api_base_url: str):
    response = api_client.get(
        f"{api_base_url}/api/onchain/agents", params={"network": "mainnet"}, timeout=40
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    for row in payload["items"]:
        assert "raw_8004scan" not in row
        assert row.get("image_url") is None
        assert isinstance(row.get("has_source_icon"), bool)
        serialized = str(row).lower()
        assert "api_key" not in serialized
        assert "x-api-key" not in serialized


def test_icon_cache_repeat_get_returns_same_bytes(api_client: requests.Session, api_base_url: str):
    agents = api_client.get(
        f"{api_base_url}/api/onchain/agents", params={"network": "mainnet"}, timeout=40
    )
    assert agents.status_code == 200
    source_agent = _pick_agent(agents.json()["items"], has_source_icon=True)
    if not source_agent:
        pytest.skip("No source-icon agent available in synced mainnet sample")

    token_id = source_agent["token_id"]
    first = api_client.get(f"{api_base_url}/api/onchain/agents/mainnet/{token_id}/icon", timeout=40)
    second = api_client.get(f"{api_base_url}/api/onchain/agents/mainnet/{token_id}/icon", timeout=40)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("X-Agent-Icon-Source") == "8004scan"
    assert second.headers.get("X-Agent-Icon-Source") == "8004scan"
    assert hashlib.sha256(first.content).hexdigest() == hashlib.sha256(second.content).hexdigest()


@dataclass
class _FakeCollection:
    doc: dict | None = None
    cached: dict | None = None
    update_calls: int = 0

    async def find_one(self, _query, _projection=None):
        if "source_hash" in _query:
            return self.cached
        return self.doc

    async def update_one(self, _query, update, upsert=False):
        self.update_calls += 1
        set_doc = update.get("$set", {})
        self.cached = {
            "content": set_doc.get("content"),
            "content_type": set_doc.get("content_type"),
            "source_hash": set_doc.get("source_hash"),
        }
        return {"ok": 1, "upsert": upsert}


class _FakeDb:
    def __init__(self, image_url: str | None):
        self.scan_agents = _FakeCollection(doc={"raw_8004scan": {"image_url": image_url}})
        self.scan_agent_icons = _FakeCollection(doc=None, cached=None)


# Icon proxy unit module tests
@pytest.mark.anyio
async def test_get_agent_icon_rejects_non_https_without_network_call(monkeypatch):
    requested = {"count": 0}

    class _NeverClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            requested["count"] += 1
            raise AssertionError("Unsafe URL should not be requested")

    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", lambda **_kwargs: _NeverClient())

    db = _FakeDb("http://example.com/icon.png")
    content, content_type, is_source = await get_agent_icon(db, 56, 123)
    assert content_type == "image/svg+xml"
    assert is_source is False
    assert content.startswith(b"<svg")
    assert requested["count"] == 0


@pytest.mark.anyio
async def test_public_https_url_rejects_private_loopback_linklocal_reserved_and_multicast(monkeypatch):
    test_ips = ["10.10.0.1", "127.0.0.1", "169.254.1.8", "240.0.0.1", "224.0.0.5"]

    for ip in test_ips:
        monkeypatch.setattr(
            icon_proxy.socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [(None, None, None, None, (ip, 443))],
        )
        safe = await _public_https_url("https://safe.example/icon.png")
        assert safe is None


@pytest.mark.anyio
async def test_public_https_url_accepts_public_address(monkeypatch):
    monkeypatch.setattr(
        icon_proxy.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("8.8.8.8", 443))],
    )
    safe = await _public_https_url("https://safe.example/icon.png")
    assert safe == "https://safe.example/icon.png"


@pytest.mark.anyio
async def test_get_agent_icon_rejects_localhost_without_network_call(monkeypatch):
    requested = {"count": 0}

    class _NeverClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            requested["count"] += 1
            raise AssertionError("Unsafe localhost URL should not be requested")

    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", lambda **_kwargs: _NeverClient())

    db = _FakeDb("https://localhost/icon.png")
    content, content_type, is_source = await get_agent_icon(db, 56, 124)
    assert content_type == "image/svg+xml"
    assert is_source is False
    assert content.startswith(b"<svg")
    assert requested["count"] == 0


@pytest.mark.anyio
async def test_get_agent_icon_rejects_redirect_oversize_and_unsupported_mime(monkeypatch):
    class _Response:
        def __init__(self, status_code: int, content_type: str, content: bytes):
            self.status_code = status_code
            self.headers = {"content-type": content_type}
            self.content = content

    class _CaseClient:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return self.response

        def stream(self, *_args, **_kwargs):
            # The proxy streams now, so the body is refused mid-read rather than
            # measured after arrival. The cases below are unchanged: a redirect,
            # an oversize body and an unsupported type must all fall back.
            response = self.response

            class _Ctx:
                async def __aenter__(self):
                    return _Streamed(response)

                async def __aexit__(self, *_):
                    return False

            return _Ctx()

    class _Streamed:
        def __init__(self, response):
            self.status_code = response.status_code
            self.headers = response.headers
            self._content = response.content

        async def aiter_bytes(self):
            for start in range(0, len(self._content), 65536):
                yield self._content[start:start + 65536]

    test_cases = [
        _Response(302, "image/png", b"abc"),
        _Response(200, "image/png", b"a" * (icon_proxy.MAX_ICON_BYTES + 1)),
        _Response(200, "image/svg+xml", b"<svg/>")
    ]

    async def fake_public_url(_value):
        return "https://safe.example/icon.png"

    monkeypatch.setattr(icon_proxy, "_public_https_url", fake_public_url)

    for idx, fake_response in enumerate(test_cases):
        monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", lambda **_kwargs: _CaseClient(fake_response))
        db = _FakeDb("https://safe.example/icon.png")
        content, content_type, is_source = await get_agent_icon(db, 56, 300 + idx)
        assert content_type == "image/svg+xml"
        assert is_source is False
        assert content.startswith(b"<svg")


@pytest.mark.anyio
async def test_get_agent_icon_uses_cached_bytes_without_network_call(monkeypatch):
    requested = {"count": 0}

    class _NeverClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            requested["count"] += 1
            raise AssertionError("Cache hit must bypass network")

    monkeypatch.setattr(icon_proxy.httpx, "AsyncClient", lambda **_kwargs: _NeverClient())

    image_url = "https://safe.example/icon.png"
    source_hash = hashlib.sha256(image_url.encode()).hexdigest()
    db = _FakeDb(image_url)
    db.scan_agent_icons.cached = {
        "content": b"\x89PNG\r\n\x1a\n\x00",
        "content_type": "image/png",
        "source_hash": source_hash,
    }

    content, content_type, is_source = await get_agent_icon(db, 56, 999)
    assert content.startswith(b"\x89PNG")
    assert content_type == "image/png"
    assert is_source is True
    assert requested["count"] == 0
