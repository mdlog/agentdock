"""Paying is the one place where guessing is expensive.

Three outcomes were previously collapsed into one another: a call that never
left the process was recorded as "paid", a facilitator that declined to settle
was recorded as "completed after settlement", and a merchant that answered a
redirect with an empty body was recorded as a free result. Each of those tells
the user something about their money that is not true.
"""

import base64
import json

import httpx
import pytest

import b402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def public_host(monkeypatch):
    async def _ok(_url):
        return None

    monkeypatch.setattr(b402, "_assert_public_https", _ok)


def _client_raising(exc):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def request(self, *_a, **_kw):
            raise exc

    return lambda **_kw: _Client()


# --- a failed call must say which kind of failure it was --------------------

@pytest.mark.parametrize("exc", [
    httpx.ConnectError("connection refused"),
    httpx.ConnectTimeout("timed out connecting"),
])
@pytest.mark.anyio
async def test_connect_failure_means_nothing_was_charged(monkeypatch, public_host, exc):
    """Nothing reached the merchant, so the authorization is still unspent and
    the attempt is safe to retry."""
    monkeypatch.setattr(b402.httpx, "AsyncClient", _client_raising(exc))

    with pytest.raises(b402.PaymentNotSent):
        await b402.call_paid("https://merchant.example/x", "hdr")


@pytest.mark.anyio
async def test_read_timeout_leaves_the_outcome_unknown(monkeypatch, public_host):
    """The request went out. It may have settled, so neither outcome may be claimed."""
    monkeypatch.setattr(b402.httpx, "AsyncClient", _client_raising(httpx.ReadTimeout("no answer")))

    with pytest.raises(b402.PaymentUncertain):
        await b402.call_paid("https://merchant.example/x", "hdr")


@pytest.mark.anyio
async def test_transport_failures_stay_inside_the_b402_error_family(monkeypatch, public_host):
    """Callers catch B402Error; an httpx error escaping it stranded the task."""
    monkeypatch.setattr(b402.httpx, "AsyncClient", _client_raising(httpx.RemoteProtocolError("bad frame")))

    with pytest.raises(b402.B402Error):
        await b402.call_paid("https://merchant.example/x", "hdr")


# --- the settlement receipt is the only proof the money moved ---------------

def _response_with(header_value=None):
    headers = {"payment-response": header_value} if header_value is not None else {}
    return httpx.Response(200, content=b"{}", headers=headers, request=httpx.Request("GET", "https://m.example/x"))


def _receipt(payload):
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_absent_receipt_reads_as_absent():
    assert b402.decode_settlement(_response_with()) is None


def test_valid_receipt_is_parsed():
    settlement = b402.decode_settlement(_response_with(_receipt({"success": True, "transaction": "0xabc"})))

    assert settlement == {"success": True, "transaction": "0xabc"}


def test_failed_settlement_is_readable_rather_than_hidden():
    settlement = b402.decode_settlement(_response_with(_receipt({"success": False, "errorReason": "insufficient_funds"})))

    assert settlement["success"] is False
    assert settlement["errorReason"] == "insufficient_funds"


def test_corrupt_receipt_is_not_mistaken_for_a_missing_one():
    """A garbled receipt says something, and it is not "no receipt" — the
    challenge decoder has always raised on this, and so must this one."""
    with pytest.raises(b402.B402Error):
        b402.decode_settlement(_response_with("!!!not base64!!!"))
