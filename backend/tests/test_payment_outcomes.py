"""Paying is the one place where guessing is expensive.

Three outcomes were previously collapsed into one another: a call that never
left the process was recorded as "paid", a facilitator that declined to settle
was recorded as "completed after settlement", and a merchant that answered a
redirect with an empty body was recorded as a free result. Each of those tells
the user something about their money that is not true.
"""

import base64
import json
from types import SimpleNamespace

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


def test_quoted_validity_window_is_never_blank():
    """Merchants may omit maxTimeoutSeconds. The signing path has always fallen
    back to 60s, so the terms shown must carry that same number rather than a
    None that renders as "Valid for: s after signing"."""
    terms = b402.describe_terms({
        "network": b402.BSC_NETWORK, "amount": "70000000000000000", "payTo": "0x" + "1" * 40,
        "asset": "0xcE24439F2D9C6a2289F741120FE202248B666666",
        "extra": {"decimals": 18, "name": "United Stables", "assetTransferMethod": "eip3009"},
    })

    assert terms["max_timeout_seconds"] == b402.DEFAULT_VALIDITY_SECONDS


def test_merchant_validity_window_is_respected_when_given():
    terms = b402.describe_terms({
        "network": b402.BSC_NETWORK, "amount": "1000", "payTo": "0x" + "1" * 40,
        "asset": "0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d",
        "maxTimeoutSeconds": 300, "extra": {"decimals": 18, "name": "USD1", "assetTransferMethod": "eip3009"},
    })

    assert terms["max_timeout_seconds"] == 300


# --- the divisor that turns a signature into a human number ------------------

USD1 = "0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d"


def _accept(**over):
    base = {"network": b402.BSC_NETWORK, "asset": USD1, "payTo": "0x" + "1" * 40,
            "amount": "70000000000000000",
            "extra": {"decimals": 18, "name": "World Liberty Financial USD", "assetTransferMethod": "eip3009"}}
    base.update(over)
    return base


def test_inflated_decimals_cannot_smuggle_a_large_transfer_past_the_ceiling():
    """The attack this exists to stop: the signature authorises a raw base-unit
    value, and only `decimals` turns it into the figure a human approves. A
    merchant claiming 30 decimals on an 18-decimal token would display
    "0.001" for a transfer of one million USD1."""
    hostile = _accept(amount=str(10**24), extra={"decimals": 30, "name": "USD1", "assetTransferMethod": "eip3009"})

    with pytest.raises(b402.PaymentRefused):
        b402.describe_terms(hostile)


def test_the_displayed_amount_uses_the_contracts_own_decimals():
    terms = b402.describe_terms(_accept(extra={"decimals": 6, "name": "lies", "assetTransferMethod": "eip3009"}))

    assert terms["decimals"] == 18
    assert terms["amount_tokens"] == pytest.approx(0.07)


def test_an_unrecognised_settlement_token_is_refused():
    """A merchant must not be able to name a token of its own making."""
    with pytest.raises(b402.PaymentRefused) as caught:
        b402.describe_terms(_accept(asset="0x" + "de" * 20))

    assert "does not recognise" in str(caught.value)


def test_the_asset_name_shown_comes_from_the_allowlist():
    terms = b402.describe_terms(_accept(extra={"decimals": 18, "name": "Definitely Not A Scam", "assetTransferMethod": "eip3009"}))

    assert terms["asset_name"] == "World Liberty Financial USD"
    assert terms["asset_symbol"] == "USD1"


def test_address_casing_does_not_defeat_the_allowlist():
    terms = b402.describe_terms(_accept(asset=USD1.lower()))

    assert terms["decimals"] == 18


def test_a_known_asset_is_preferred_over_an_unverifiable_one():
    challenge = {"accepts": [
        {"network": b402.BSC_NETWORK, "asset": "0x" + "ab" * 20, "extra": {"assetTransferMethod": "eip3009"}},
        _accept(),
    ]}

    assert b402.select_bsc_eip3009(challenge)["asset"] == USD1


# --- the signature has to travel under the name the merchant reads -----------
#
# x402 v2 dropped the non-standard X- prefix: X-PAYMENT became
# PAYMENT-SIGNATURE. This module already read the v2 names on the way in
# (payment-required, payment-response) while sending the v1 name on the way
# out, and no real settlement had ever run to catch it.


def _recording_client(statuses):
    """A client that answers with `statuses` in order and records every call."""
    sent: list[dict] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def request(self, method, url, headers=None, **_kw):
            sent.append({"method": method, "url": url, "headers": headers or {}})
            status = statuses[min(len(sent) - 1, len(statuses) - 1)]
            return httpx.Response(status, content=b"{}", request=httpx.Request(method, url))

    return sent, (lambda **_kw: _Client())


@pytest.mark.anyio
async def test_a_v2_merchant_is_paid_under_the_v2_header(monkeypatch, public_host):
    sent, client = _recording_client([200])
    monkeypatch.setattr(b402.httpx, "AsyncClient", client)

    await b402.call_paid("https://merchant.example/x", "hdr", x402_version=2)

    assert sent[0]["headers"].get("PAYMENT-SIGNATURE") == "hdr"
    assert "X-PAYMENT" not in sent[0]["headers"]


@pytest.mark.anyio
async def test_a_v1_merchant_is_paid_under_the_legacy_header(monkeypatch, public_host):
    sent, client = _recording_client([200])
    monkeypatch.setattr(b402.httpx, "AsyncClient", client)

    await b402.call_paid("https://merchant.example/x", "hdr", x402_version=1)

    assert sent[0]["headers"].get("X-PAYMENT") == "hdr"
    assert "PAYMENT-SIGNATURE" not in sent[0]["headers"]


@pytest.mark.anyio
async def test_a_merchant_that_still_reads_the_old_name_is_retried_once(monkeypatch, public_host):
    """Deployed middleware mixes the two vocabularies — one live merchant
    advertises PAYMENT-REQUIRED and X-PAYMENT-RESPONSE in the same CORS header.
    A 402 says the payment was not taken, and the same authorization cannot
    settle twice regardless, because EIP-3009 spends its nonce on first use."""
    sent, client = _recording_client([402, 200])
    monkeypatch.setattr(b402.httpx, "AsyncClient", client)

    response = await b402.call_paid("https://merchant.example/x", "hdr", x402_version=2)

    assert [h for call in sent for h in ("PAYMENT-SIGNATURE", "X-PAYMENT") if h in call["headers"]] \
        == ["PAYMENT-SIGNATURE", "X-PAYMENT"]
    assert response.status_code == 200


@pytest.mark.anyio
async def test_an_accepted_payment_is_never_presented_a_second_time(monkeypatch, public_host):
    sent, client = _recording_client([200])
    monkeypatch.setattr(b402.httpx, "AsyncClient", client)

    await b402.call_paid("https://merchant.example/x", "hdr")

    assert len(sent) == 1


@pytest.mark.anyio
async def test_a_merchant_that_refuses_under_both_names_is_answered_with_its_402(monkeypatch, public_host):
    """Two 402s are a refusal, not a transport failure: the caller has to see
    the merchant's own status rather than a retry loop swallowing it."""
    sent, client = _recording_client([402, 402])
    monkeypatch.setattr(b402.httpx, "AsyncClient", client)

    response = await b402.call_paid("https://merchant.example/x", "hdr")

    assert len(sent) == 2
    assert response.status_code == 402


def test_the_payload_declares_the_version_the_merchant_quoted():
    """A v1 merchant reading `x402Version: 2` in the payload it was handed is
    the same mismatch as the header name, one layer down."""
    payload = json.loads(base64.b64decode(
        b402.build_payment_header(_accept(), "0x" + "11" * 65, {"from": "0x" + "1" * 40}, x402_version=1)))

    assert payload["x402Version"] == 1


def test_the_payload_declares_v2_by_default():
    payload = json.loads(base64.b64decode(
        b402.build_payment_header(_accept(), "0x" + "11" * 65, {"from": "0x" + "1" * 40})))

    assert payload["x402Version"] == 2


def test_the_version_is_read_from_the_option_being_paid():
    """Merchants repeat it per accept; one lists v2 options next to v1 ones."""
    accept = {**_accept(), "x402Version": 1}

    assert b402.challenge_version({"x402Version": 2, "accepts": [accept]}, accept) == 1


def test_the_version_falls_back_to_the_challenge_then_to_v2():
    assert b402.challenge_version({"x402Version": 1, "accepts": []}, _accept()) == 1
    assert b402.challenge_version({"accepts": []}, _accept()) == 2


# --- and the version has to survive the trip from quote to signature ---------
#
# The quote and the payment are two requests minutes apart, with a wallet
# signature in between. A version read at quote time and dropped before the
# replay would leave the header name to a default rather than to the merchant.


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    async def find_one(self, query, *_a, **_kw):
        return next((dict(d) for d in self.docs if self._matches(d, query)), None)

    async def update_one(self, query, update, *_a, **_kw):
        matched = [d for d in self.docs if self._matches(d, query)]
        for doc in matched:
            doc.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=len(matched))

    async def insert_one(self, doc, *_a, **_kw):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))


class _Db:
    def __init__(self, task, resource):
        self.tasks = _Collection([task])
        self.b402_resources = _Collection([resource])
        self.audit_events = _Collection()


RESOURCE = {"id": "b402-test", "resource": "https://merchant.example/x"}


def _task(**over):
    task = {"id": "task-1", "agent_id": RESOURCE["id"], "state": "payment_pending",
            "objective": "list the pools", "b402_method": "GET",
            "b402_accept": _accept(), "b402_authorization": {"from": "0x" + "1" * 40}}
    task.update(over)
    return task


@pytest.mark.anyio
async def test_the_version_the_merchant_quoted_is_the_version_it_is_paid_in(monkeypatch):
    """A v1 merchant must not be replayed in v2's dialect. Both the header name
    and the payload's own x402Version follow the quote that was signed."""
    import server
    from models import PayRequest

    presented: dict = {}

    async def _record(url, header, method="GET", params=None, x402_version=2):
        presented.update(header=header, x402_version=x402_version)
        return httpx.Response(200, content=b"{}", request=httpx.Request("GET", url))

    monkeypatch.setattr(server, "db", _Db(_task(b402_x402_version=1), RESOURCE))
    monkeypatch.setattr(server.b402, "call_paid", _record)

    await server.pay_task("task-1", PayRequest(signature="0x" + "ab" * 65))

    assert presented["x402_version"] == 1
    assert json.loads(base64.b64decode(presented["header"]))["x402Version"] == 1


@pytest.mark.anyio
async def test_the_quote_records_which_version_the_merchant_speaks(monkeypatch):
    import server

    challenge = {"x402Version": 1, "accepts": [_accept()]}

    async def _challenge(url, params=None):
        return challenge, httpx.Response(402, content=b"{}", request=httpx.Request("GET", url)), "GET"

    db = _Db(_task(state="created"), RESOURCE)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.b402, "fetch_challenge", _challenge)

    await server._run_b402("task-1", _task(state="created"))

    assert db.tasks.docs[0]["b402_x402_version"] == 1
