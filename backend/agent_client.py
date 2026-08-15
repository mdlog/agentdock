"""Call a live ERC-8004 agent endpoint and return its real output.

These endpoints come from third-party on-chain metadata, so every call reuses the
same SSRF posture as the icon proxy and the b402 client: HTTPS only, public host
only, no redirects, bounded time and size. Two transports are supported — MCP
(JSON-RPC over HTTP) and A2A (message/send) — because those are what 8004scan
agents actually declare. Nothing here holds a key or moves funds; a paid agent
answers 402 and is handed to the b402 flow instead.
"""

import asyncio
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

CALL_TIMEOUT = httpx.Timeout(45, connect=10)
MAX_RESPONSE_BYTES = 1_500_000
USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"


class AgentCallError(RuntimeError):
    pass


class AgentPaymentRequired(RuntimeError):
    """The endpoint answered 402 — route to the b402/x402 payment flow instead."""


async def _assert_public_https(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host in {"localhost", "0.0.0.0"}:
        raise AgentCallError("Agent endpoint must be public HTTPS")
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise AgentCallError("Agent endpoint host could not be resolved") from exc
    for row in records:
        ip = ipaddress.ip_address(row[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise AgentCallError("Agent endpoint resolves to a non-public address")


def pick_endpoint(detail: dict[str, Any]) -> tuple[str, str] | None:
    """Return (kind, url) for the first usable endpoint, or None."""
    if detail.get("mcp_server"):
        return "mcp", detail["mcp_server"]
    if detail.get("a2a_endpoint"):
        return "a2a", detail["a2a_endpoint"]
    if detail.get("agent_url"):
        return "a2a", detail["agent_url"]
    return None


def _sse_or_json(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except ValueError:
                continue
    try:
        return json.loads(text)
    except ValueError:
        return None


def _guard_response(response: httpx.Response) -> None:
    if response.status_code == 402:
        raise AgentPaymentRequired("Agent requires payment")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise AgentCallError("Agent response exceeded the size limit")


async def _post(client: httpx.AsyncClient, url: str, payload: dict, session: str | None = None) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    response = await client.post(url, json=payload, headers=headers)
    _guard_response(response)
    return response


async def call_mcp(url: str, objective: str) -> dict[str, Any]:
    """initialize -> tools/list -> call a chat-like tool if present, else report tools."""
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
        init = await _post(client, url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "agentdock", "version": "1.0"}}})
        session = init.headers.get("mcp-session-id") or init.headers.get("Mcp-Session-Id")
        listed = await _post(client, url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
        tools = ((_sse_or_json(listed.text) or {}).get("result") or {}).get("tools") or []
        names = [t.get("name") for t in tools]
        chat = next((t for t in tools if t.get("name") in ("chat", "ask", "message", "query", "prompt")), None)
        if chat:
            arg_key = next(iter((chat.get("inputSchema") or {}).get("properties") or {"message": {}}), "message")
            called = await _post(client, url, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": chat["name"], "arguments": {arg_key: objective}}}, session)
            result = _sse_or_json(called.text) or {}
            content = ((result.get("result") or {}).get("content") or [])
            text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text") or json.dumps(result.get("result") or result)[:2000]
            return {"transport": "mcp", "tool": chat["name"], "tools": names, "output": text[:4000]}
        # No conversational tool: the agent's real, callable capabilities ARE the result.
        summary = "This agent exposes the following live tools:\n" + "\n".join(
            f"• {t.get('name')}: {str(t.get('description') or '')[:100]}" for t in tools[:20]) if tools else "The agent responded but declared no callable tools."
        return {"transport": "mcp", "tools": names, "output": summary}


async def call_a2a(url: str, objective: str) -> dict[str, Any]:
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
        response = await _post(client, url, {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {
            "message": {"role": "user", "parts": [{"kind": "text", "text": objective}], "messageId": "agentdock-1"}}})
        data = _sse_or_json(response.text) or {}
        result = data.get("result") or data
        parts = []
        for msg in ([result] if isinstance(result, dict) else []):
            for part in (msg.get("parts") or (msg.get("message") or {}).get("parts") or []):
                if part.get("kind") == "text" or "text" in part:
                    parts.append(part.get("text", ""))
        text = "\n".join(p for p in parts if p) or json.dumps(result)[:2000]
        return {"transport": "a2a", "output": text[:4000]}


async def call_agent(kind: str, url: str, objective: str) -> dict[str, Any]:
    if kind == "mcp":
        return await call_mcp(url, objective)
    return await call_a2a(url, objective)
