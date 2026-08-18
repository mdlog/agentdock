"""Binance b402 (x402 v2) buyer-side client.

AgentDock is the payer, never the merchant. Paying is permissionless: no partner
credentials, no onboarding — only a wallet, and the wallet is the user's. This
module never holds or sees a private key. It reads a merchant's 402 challenge,
produces the EIP-712 payload for the user's browser wallet to sign, and replays
the request with the signature the browser sends back.
"""

import asyncio
import base64
import hashlib
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from scan8004 import derive_categories

BAZAAR_BASE = "https://www.binance.com/bapi/ramp/v1/public/ramp/b402"
BSC_NETWORK = "eip155:56"
BSC_CHAIN_ID = 56

# The Bazaar index and the live challenge disagree in practice (a resource listed
# as BSC/USD1 answered with a Solana offer), so the live challenge is always the
# authority for what gets signed. The catalog is used for discovery only.
CATALOG_TIMEOUT = httpx.Timeout(30, connect=20)
CHALLENGE_TIMEOUT = httpx.Timeout(30, connect=10)
CALL_TIMEOUT = httpx.Timeout(90, connect=10)
MAX_RESPONSE_BYTES = 2_000_000

# Merchants may quote any amount they like. Anything above this is refused and
# shown to the user rather than signed, because the figure comes from a third
# party we do not control. Denominated in whole tokens (all BSC assets are 18dp).
MAX_AMOUNT_TOKENS = 1.0

# Used when the merchant quotes no validity window of its own.
DEFAULT_VALIDITY_SECONDS = 60

USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"

# x402 v2 dropped the non-standard X- prefix: X-PAYMENT became PAYMENT-SIGNATURE
# and X-PAYMENT-RESPONSE became PAYMENT-RESPONSE — the two names this module
# already reads on the way in. Presenting a signature under the v1 name to a v2
# merchant is a header nobody looks at, and no settlement has run for real yet
# that would have caught it.
PAYMENT_HEADER_V2 = "PAYMENT-SIGNATURE"
PAYMENT_HEADER_V1 = "X-PAYMENT"

# Settlement assets AgentDock will present for signing, with the decimals read
# from each contract on BNB Chain — not from the merchant.
#
# The signature authorises a raw base-unit value; only `decimals` turns that
# into the figure a human approves. A merchant that declares 30 decimals on an
# 18-decimal token shows the user "0.000001" for a transfer of one million,
# and the spend ceiling below waves it through. Nothing about the quote is
# trustworthy, so the divisor cannot come from it.
#
# Verified on-chain via decimals(): USD1 18, U 18.
BSC_SETTLEMENT_ASSETS = {
    "0x8d0d000ee44948fc98c9b98a4fa4921476f08b0d": {"symbol": "USD1", "name": "World Liberty Financial USD", "decimals": 18},
    "0xce24439f2d9c6a2289f741120fe202248b666666": {"symbol": "U", "name": "United Stables", "decimals": 18},
}

TRANSFER_WITH_AUTHORIZATION_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


class B402Error(RuntimeError):
    pass


class PaymentRefused(B402Error):
    """The merchant's terms are outside what we are willing to present for signing."""


class PaymentNotSent(B402Error):
    """The paid request never left this process, so nothing can have been charged."""


class PaymentUncertain(B402Error):
    """The paid request went out but its outcome is unknown — it may have settled."""


async def _assert_public_https(url: str) -> None:
    """Same SSRF posture as the icon proxy: endpoints come from third-party data."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host in {"localhost", "0.0.0.0"}:
        raise B402Error("Resource must be served over HTTPS from a public host")
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise B402Error("Resource host could not be resolved") from exc
    for row in records:
        ip = ipaddress.ip_address(row[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise B402Error("Resource host resolves to a non-public address")


def _decode_challenge(response: httpx.Response) -> dict[str, Any] | None:
    raw = response.headers.get("payment-required")
    if raw:
        try:
            return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        except (ValueError, TypeError) as exc:
            raise B402Error("Merchant sent an unreadable payment challenge") from exc
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) and "x402Version" in body else None


def select_bsc_eip3009(challenge: dict[str, Any]) -> dict[str, Any]:
    """Pick a BNB Chain option settled by EIP-3009.

    Merchants list several options and BNB Chain is often not the first, so an
    implementation that grabbed accepts[0] would pay on the wrong chain. EIP-3009
    is required rather than preferred: permit2 needs a separate approval
    transaction, which would cost the user gas before anything is signed here.
    """
    accepts = challenge.get("accepts") or []
    on_bsc = [a for a in accepts if a.get("network") == BSC_NETWORK]
    if not on_bsc:
        networks = sorted({str(a.get("network")) for a in accepts}) or ["none"]
        raise PaymentRefused(f"This resource does not accept payment on BNB Chain (offers: {', '.join(networks)})")
    usable = [a for a in on_bsc if (a.get("extra") or {}).get("assetTransferMethod") == "eip3009"]
    if not usable:
        raise PaymentRefused("This resource only accepts permit2 on BNB Chain, which needs a separate approval transaction")
    # Prefer an option in an asset we can verify; refusing here beats refusing
    # later in describe_terms, which would discard a usable alternative.
    known = [a for a in usable if str(a.get("asset") or "").strip().lower() in BSC_SETTLEMENT_ASSETS]
    return (known or usable)[0]


def trusted_asset(accept: dict[str, Any]) -> dict[str, Any]:
    """The allow-listed asset this quote settles in, or a refusal.

    Doubles as a check on the contract itself: an unknown address is refused
    rather than signed for, so a merchant cannot name a token of its own making.
    """
    address = str(accept.get("asset") or "").strip().lower()
    known = BSC_SETTLEMENT_ASSETS.get(address)
    if not known:
        raise PaymentRefused(
            "This merchant settles in a token AgentDock does not recognise, so its terms cannot be verified")
    return known


def describe_terms(accept: dict[str, Any]) -> dict[str, Any]:
    """Human-checkable terms. Shown before anything is signed."""
    extra = accept.get("extra") or {}
    raw_amount = str(accept.get("amount") or accept.get("maxAmountRequired") or "0")
    try:
        amount = int(raw_amount)
    except ValueError as exc:
        raise B402Error("Merchant quoted an unreadable amount") from exc
    asset = trusted_asset(accept)
    decimals = asset["decimals"]
    tokens = amount / (10 ** decimals)
    if tokens > MAX_AMOUNT_TOKENS:
        raise PaymentRefused(f"Merchant asked for {tokens:g} tokens, above the {MAX_AMOUNT_TOKENS:g} ceiling AgentDock will present for signing")
    return {
        "network": accept.get("network"),
        "chain_id": BSC_CHAIN_ID,
        "asset": accept.get("asset"),
        # The name shown is the one the contract carries, not the one the
        # merchant supplied alongside it.
        "asset_name": asset["name"],
        "asset_symbol": asset["symbol"],
        "amount_raw": raw_amount,
        "amount_tokens": tokens,
        "decimals": decimals,
        "pay_to": accept.get("payTo"),
        # Merchants may omit this. authorize_task has always fallen back to 60s
        # when minting the authorization, so the figure shown to the user is the
        # same one their signature will actually carry.
        "max_timeout_seconds": int(accept.get("maxTimeoutSeconds") or DEFAULT_VALIDITY_SECONDS),
        "transfer_method": extra.get("assetTransferMethod"),
    }


def build_typed_data(accept: dict[str, Any], payer: str, valid_after: int, valid_before: int, nonce: str) -> dict[str, Any]:
    """EIP-712 TransferWithAuthorization for the user's wallet to sign.

    Returned to the browser; the signature comes back and never passes through a
    key held here.
    """
    extra = accept.get("extra") or {}
    return {
        "domain": {
            "name": extra.get("name"),
            "version": extra.get("version"),
            "chainId": BSC_CHAIN_ID,
            "verifyingContract": accept.get("asset"),
        },
        "types": TRANSFER_WITH_AUTHORIZATION_TYPES,
        "primaryType": "TransferWithAuthorization",
        "message": {
            "from": payer,
            "to": accept.get("payTo"),
            "value": str(accept.get("amount") or accept.get("maxAmountRequired")),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce,
        },
    }


def challenge_version(challenge: dict[str, Any], accept: dict[str, Any]) -> int:
    """Which x402 version this quote speaks.

    Merchants repeat the figure inside each option, and the option being paid is
    the one whose word counts; the top-level figure is the fallback. Every b402
    merchant on BNB Chain answers v2, so a challenge that states nothing is read
    as v2 rather than as the older dialect.
    """
    for source in (accept, challenge):
        try:
            return int(source.get("x402Version"))
        except (TypeError, ValueError):
            continue
    return 2


def _header_names(x402_version: int) -> list[str]:
    """The name to present the signature under, then the one to fall back to.

    Deployed middleware mixes the two vocabularies — one live merchant answers
    with a v2 `payment-required` challenge while advertising `X-PAYMENT-RESPONSE`
    in its own CORS headers. A 402 says the merchant did not take the payment, so
    the other name is worth exactly one retry; and the same authorization cannot
    settle twice either way, because EIP-3009 spends its nonce on first use.
    """
    ordered = [PAYMENT_HEADER_V2, PAYMENT_HEADER_V1]
    return ordered if x402_version >= 2 else ordered[::-1]


def build_payment_header(accept: dict[str, Any], signature: str, authorization: dict[str, Any],
                         x402_version: int = 2) -> str:
    payload = {
        "x402Version": x402_version,
        "scheme": accept.get("scheme") or "exact",
        "network": accept.get("network"),
        "payload": {"signature": signature, "authorization": authorization},
    }
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_settlement(response: httpx.Response) -> dict[str, Any] | None:
    raw = response.headers.get("payment-response")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError) as exc:
        # Same posture as _decode_challenge: a merchant that sends a garbled
        # receipt has told us something, and it is not "no receipt".
        raise B402Error("Merchant sent an unreadable settlement receipt") from exc


def _request_args(method: str, params: dict | None) -> dict:
    # A GET carries params in the query string; a POST carries them in the JSON
    # body, which is what these merchants expect.
    if method == "POST":
        return {"json": params or {}}
    return {"params": params}


async def fetch_challenge(url: str, params: dict | None = None) -> tuple[dict[str, Any] | None, httpx.Response, str]:
    """Call the resource unpaid. A 200 means it is free; a 402 carries the terms.

    The b402 catalogue does not record which HTTP method an endpoint wants, and
    ~half of them answer 404 to GET but 402 to POST (verified: all of Xona,
    BortAgent). So GET is tried first, and a 404/405 falls back to POST. The
    method that produced the challenge is returned so the paid replay uses the
    same one.
    """
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CHALLENGE_TIMEOUT, follow_redirects=False) as client:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        response = await client.request("GET", url, headers=headers, **_request_args("GET", params))
        method = "GET"
        if response.status_code in (404, 405):
            post = await client.request("POST", url, headers=headers, **_request_args("POST", params))
            if post.status_code == 402 or post.status_code < 400:
                response, method = post, "POST"
    return _decode_challenge(response), response, method


async def call_paid(url: str, header: str, method: str = "GET", params: dict | None = None,
                    x402_version: int = 2) -> httpx.Response:
    """Present the signed authorization and return the merchant's response.

    The signature travels under the header name the merchant's own version
    reads, and a 402 — which says the payment was not taken — is retried once
    under the other name; see _header_names for why both still occur in the wild.

    Transport failures are translated rather than allowed to escape, and the two
    kinds are kept apart because they mean opposite things to the payer: if the
    connection was never established the authorization was never presented, so
    nothing can have been charged and the call is safe to retry. Once the
    request is on the wire, a timeout proves nothing either way.
    """
    await _assert_public_https(url)
    try:
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
            for name in _header_names(x402_version):
                response = await client.request(
                    method, url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json", name: header},
                    **_request_args(method, params),
                )
                if response.status_code != 402:
                    break
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol) as exc:
        raise PaymentNotSent(f"The agent could not be reached ({type(exc).__name__}), so nothing was charged") from exc
    except httpx.HTTPError as exc:
        raise PaymentUncertain(f"The paid call was sent but its outcome is unknown ({type(exc).__name__})") from exc
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise B402Error("Agent response exceeded the size limit")
    return response


# The whole check, both methods included. Asking twice doubles what a hanging
# host can cost, and the catalogue sync walks every listing in turn.
CHECK_TIMEOUT_SECONDS = 25


async def check_resource(url: str) -> tuple[bool, str]:
    """Whether a bazaar resource actually answers with payment terms.

    Asked the way hiring asks it — through fetch_challenge, fallback to POST
    included. A bare GET here reported "Answered HTTP 404 instead of payment
    terms" for every Xona and BortAgent listing while the hire path was getting
    a signed 402 out of the same URL by posting to it, exactly as the comment on
    fetch_challenge says it would. The catalogue was understating its own payable
    supply — 12 listings of 35 rather than 33 — and understating supply is the
    same failure as overstating it.

    Anything else — a 404 both ways, a timeout, an empty 200 — means the listing
    cannot be hired, and the catalogue should say so rather than let the visitor
    discover it at the final step.
    """
    try:
        challenge, response, method = await asyncio.wait_for(fetch_challenge(url), CHECK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return False, f"Did not answer within {CHECK_TIMEOUT_SECONDS}s"
    except (B402Error, httpx.HTTPError) as exc:
        return False, f"{type(exc).__name__}: {exc}"[:200]
    if challenge:
        return True, f"Answered 402 with payment terms ({method})"
    # A 2xx means the resource serves without payment — odd for a paid listing,
    # but a visitor can still use it, so it is not a dead end.
    if response.status_code < 300:
        return True, f"Answered HTTP {response.status_code} without requiring payment"
    return False, f"Answered HTTP {response.status_code} instead of payment terms"


async def fetch_bazaar(limit: int = 100, max_pages: int = 20) -> list[dict[str, Any]]:
    """Discovery only. Terms are never taken from here — see fetch_challenge.

    Pages by `offset`. The API also accepts a `page` parameter but ignores it —
    page=2 returns the same rows as page=1 — so anything past the first `limit`
    would be silently lost if this paged the obvious way.
    """
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    async with httpx.AsyncClient(timeout=CATALOG_TIMEOUT) as client:
        for _ in range(max_pages):
            try:
                response = await client.get(
                    f"{BAZAAR_BASE}/bazaar/resources",
                    params={"offset": offset, "limit": limit},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json().get("data") or {}
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                raise B402Error("b402 Bazaar catalog is unavailable") from exc
            items = data.get("items") or []
            fresh = [item for item in items if item.get("resource") not in seen]
            for item in fresh:
                seen.add(item.get("resource"))
            collected.extend(fresh)
            total = (data.get("pagination") or {}).get("total")
            # Stop on a page that added nothing new, so an API that ignores the
            # offset cannot spin this loop.
            if not fresh or (isinstance(total, int) and len(collected) >= total):
                break
            offset += limit
    return collected


def bazaar_projection(item: dict[str, Any]) -> dict[str, Any] | None:
    """Public projection of a catalog entry, restricted to BNB Chain listings."""
    resource = item.get("resource")
    if not resource or not resource.startswith("https://"):
        return None
    accepts = [a for a in (item.get("accepts") or []) if a.get("network") == BSC_NETWORK]
    if not accepts:
        return None
    host = (urlparse(resource).hostname or "").lower()
    description = item.get("description") or ""
    # Stable across processes: str.__hash__ is salted per interpreter run, so an
    # id built from it would change on every restart and break stored task links.
    return {
        "id": "b402-" + hashlib.sha256(resource.encode()).hexdigest()[:16],
        "resource": resource,
        "host": host,
        "type": item.get("type"),
        "description": description,
        # Same four-category taxonomy as the onchain identities, so a category
        # selected in the marketplace can surface the hireable services in it.
        "categories": derive_categories(host, description),
        "x402_version": item.get("x402Version"),
        "listed_assets": sorted({a.get("asset") for a in accepts if a.get("asset")}),
        "pay_to": sorted({a.get("payTo") for a in accepts if a.get("payTo")}),
        "source": "b402_bazaar",
        "source_label": "b402 Bazaar · BNB Chain",
    }
