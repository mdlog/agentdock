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

USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"

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
    return usable[0]


def describe_terms(accept: dict[str, Any]) -> dict[str, Any]:
    """Human-checkable terms. Shown before anything is signed."""
    extra = accept.get("extra") or {}
    raw_amount = str(accept.get("amount") or accept.get("maxAmountRequired") or "0")
    try:
        amount = int(raw_amount)
    except ValueError as exc:
        raise B402Error("Merchant quoted an unreadable amount") from exc
    decimals = int(extra.get("decimals") or 18)
    tokens = amount / (10 ** decimals)
    if tokens > MAX_AMOUNT_TOKENS:
        raise PaymentRefused(f"Merchant asked for {tokens:g} tokens, above the {MAX_AMOUNT_TOKENS:g} ceiling AgentDock will present for signing")
    return {
        "network": accept.get("network"),
        "chain_id": BSC_CHAIN_ID,
        "asset": accept.get("asset"),
        "asset_name": extra.get("name"),
        "amount_raw": raw_amount,
        "amount_tokens": tokens,
        "decimals": decimals,
        "pay_to": accept.get("payTo"),
        "max_timeout_seconds": accept.get("maxTimeoutSeconds"),
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


def build_payment_header(accept: dict[str, Any], signature: str, authorization: dict[str, Any]) -> str:
    payload = {
        "x402Version": 2,
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
    except (ValueError, TypeError):
        return None


async def fetch_challenge(url: str, method: str = "GET", params: dict | None = None) -> tuple[dict[str, Any] | None, httpx.Response]:
    """Call the resource unpaid. A 200 means it is free; a 402 carries the terms."""
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CHALLENGE_TIMEOUT, follow_redirects=False) as client:
        response = await client.request(method, url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    return _decode_challenge(response), response


async def call_paid(url: str, header: str, method: str = "GET", params: dict | None = None) -> httpx.Response:
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
        response = await client.request(
            method, url, params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", "X-PAYMENT": header},
        )
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise B402Error("Agent response exceeded the size limit")
    return response


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
    # Stable across processes: str.__hash__ is salted per interpreter run, so an
    # id built from it would change on every restart and break stored task links.
    return {
        "id": "b402-" + hashlib.sha256(resource.encode()).hexdigest()[:16],
        "resource": resource,
        "host": host,
        "type": item.get("type"),
        "description": item.get("description") or "",
        "x402_version": item.get("x402Version"),
        "listed_assets": sorted({a.get("asset") for a in accepts if a.get("asset")}),
        "pay_to": sorted({a.get("payTo") for a in accepts if a.get("payTo")}),
        "source": "b402_bazaar",
        "source_label": "b402 Bazaar · BNB Chain",
    }
