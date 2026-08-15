import asyncio
import hashlib
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bson.binary import Binary


MAX_ICON_BYTES = 1_000_000
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def fallback_svg(chain_id: int, token_id: int) -> bytes:
    digest = hashlib.sha256(f"{chain_id}:{token_id}".encode()).digest()
    palette = ("#0F766E", "#14B8A6", "#FACC15", "#172033", "#F8FAFC")
    bg, shape, accent = palette[digest[0] % 5], palette[digest[1] % 5], palette[digest[2] % 5]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
    <rect width="64" height="64" rx="10" fill="{bg}"/>
    <circle cx="{18 + digest[3] % 28}" cy="{17 + digest[4] % 26}" r="{11 + digest[5] % 10}" fill="{shape}"/>
    <path d="M8 55 Q32 {20 + digest[6] % 24} 56 55 Z" fill="{accent}"/>
    </svg>'''
    return svg.encode()


async def _public_https_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host in {"localhost", "0.0.0.0"}:
        return None
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
        addresses = {row[4][0] for row in records}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return None
    except (OSError, ValueError):
        return None
    return value


async def get_agent_icon(db, chain_id: int, token_id: int) -> tuple[bytes, str, bool]:
    agent = await db.scan_agents.find_one(
        {"chain_id": chain_id, "token_id": token_id},
        {"_id": 0, "raw_8004scan.image_url": 1},
    )
    if not agent:
        return fallback_svg(chain_id, token_id), "image/svg+xml", False
    source_url = agent.get("raw_8004scan", {}).get("image_url")
    source_hash = hashlib.sha256((source_url or "").encode()).hexdigest()
    cached = await db.scan_agent_icons.find_one(
        {"chain_id": chain_id, "token_id": token_id, "source_hash": source_hash},
        {"_id": 0, "content": 1, "content_type": 1},
    )
    if cached:
        return bytes(cached["content"]), cached["content_type"], True

    safe_url = await _public_https_url(source_url)
    if safe_url:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
                response = await client.get(safe_url, headers={"Accept": "image/png,image/jpeg,image/webp,image/gif", "User-Agent": "AgentDock-IconProxy/1.0"})
            content_type = response.headers.get("content-type", "").split(";")[0].lower()
            if response.status_code == 200 and content_type in ALLOWED_TYPES and 0 < len(response.content) <= MAX_ICON_BYTES:
                await db.scan_agent_icons.update_one(
                    {"chain_id": chain_id, "token_id": token_id},
                    {"$set": {"source_hash": source_hash, "content": Binary(response.content), "content_type": content_type}},
                    upsert=True,
                )
                return response.content, content_type, True
        except (httpx.HTTPError, ValueError):
            pass
    return fallback_svg(chain_id, token_id), "image/svg+xml", False