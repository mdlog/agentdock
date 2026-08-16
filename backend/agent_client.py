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
# Probes run across hundreds of third-party hosts, so they give up far sooner
# than a real call: a slow endpoint is not one a judge should be sent to.
PROBE_TIMEOUT = httpx.Timeout(12, connect=6)
# Hard ceiling for one probe including DNS, which httpx timeouts do not cover.
PROBE_WALL_CLOCK = 30.0
MAX_RESPONSE_BYTES = 1_500_000
USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"
# Sent only when a read-only lookup left the verdict ambiguous. Kept short and
# self-identifying so an operator reading their logs knows what it was.
PROBE_MESSAGE = "AgentDock liveness check. Any reply confirms you are callable."


class AgentCallError(RuntimeError):
    """The endpoint could not be reached safely."""


class AgentPaymentRequired(RuntimeError):
    """The endpoint answered 402 — route to the b402/x402 payment flow instead."""


class AgentRejected(AgentCallError):
    """The endpoint answered, but with a refusal rather than a result.

    Worth its own type because it is not a network failure: the agent is up and
    reachable, it simply did not do the work. Both transports are JSON-RPC 2.0,
    so a refusal usually arrives as an ordinary HTTP 200 carrying an `error`
    member — reading only `result` is how "Unauthorized" ends up rendered to the
    user as the agent's answer.
    """

    def __init__(self, message: str, *, reason: str = "upstream_error"):
        super().__init__(message)
        self.reason = reason  # auth | payment | upstream_error | empty | unreadable


# Substrings that mark a refusal as "the agent wants a credential we do not
# hold" rather than "the agent is broken". Kept deliberately narrow: a false
# positive here only changes the wording shown to the user, never whether the
# call is treated as a failure.
_AUTH_HINTS = ("unauthor", "forbidden", "api key", "apikey", "api-key", "access denied",
               "credential", "authenticate", "authentication", "not permitted", "invalid token")


def _looks_like_auth(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _AUTH_HINTS)


# A platform saying an agent is registered but not serving is a different fact
# from an unreachable host, and the user deserves the difference.
_UNBOUND_HINTS = ("not open to inbound", "not accepting", "no endpoint bound", "unbound",
                  "not deployed", "agent is offline", "no service attached")


def _looks_unbound(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _UNBOUND_HINTS)


# When a shared endpoint answers that it needs the agent's id in the path, it has
# told us its convention. Following it is not a guess — the retry either reaches
# that agent or is refused by name.
_NEEDS_ID_HINTS = ("tokenid is required", "agentid", "agent id is required", "/:agentid")


def _asks_for_agent_id(text: str) -> bool:
    low = text.lower().replace("_", "")
    return any(hint.replace("_", "") in low for hint in _NEEDS_ID_HINTS)


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
    if response.status_code in (401, 403):
        raise AgentRejected(f"The agent requires its own credential (HTTP {response.status_code}).", reason="auth")
    if response.status_code >= 400:
        raise AgentRejected(f"The agent endpoint answered HTTP {response.status_code}.", reason="upstream_error")


def _unwrap(envelope: dict[str, Any] | None, step: str, *, tolerate_bare: bool = False) -> dict[str, Any]:
    """Return the JSON-RPC result, raising when the peer answered an error.

    `tolerate_bare` keeps working with the registered agents that reply with the
    payload object directly instead of wrapping it in a JSON-RPC envelope.
    """
    if envelope is None:
        raise AgentRejected(f"The agent's {step} reply was not readable JSON.", reason="unreadable")

    error = envelope.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = str(error.get("message") or error.get("data") or "no message given")
        reason = "auth" if _looks_like_auth(f"{code} {message}") else "upstream_error"
        suffix = f" (code {code})" if code is not None else ""
        raise AgentRejected(f"The agent refused the {step} call: {message}{suffix}", reason=reason)

    result = envelope.get("result")
    if result is None:
        if tolerate_bare and any(k in envelope for k in ("parts", "message", "artifacts", "status", "kind")):
            return envelope
        raise AgentRejected(f"The agent answered {step} with neither a result nor an error.", reason="empty")
    return result if isinstance(result, dict) else {"value": result}


# Placeholders a platform leaves in the URL it registers on-chain. Substituting
# the agent's own token id is not a guess: the card that comes back carries the
# id and name, and resolve_a2a_endpoint refuses it unless they match.
_ID_PLACEHOLDERS = ("{agentId}", "{agent_id}", "{tokenId}", "{token_id}", "{id}", "%7BagentId%7D")


def substitute_agent_id(url: str, token_id: int | None) -> str:
    if token_id is None:
        return url
    for placeholder in _ID_PLACEHOLDERS:
        url = url.replace(placeholder, str(token_id))
    return url


# Which parameterless tools may be called on the user's behalf when the agent
# has no conversational tool. Two gates, both required: the name must look
# read-only, and must not contain anything that smells like a state change.
# The mutation list wins on conflict — a tool named "get_and_execute" is out.
_READONLY_PREFIXES = ("get", "list", "show", "read", "query", "stats", "overview",
                      "recommend", "top_", "info", "describe", "fetch", "check")
_MUTATION_WORDS = ("build", "swap", "borrow", "repay", "mint", "redeem", "deposit",
                   "withdraw", "vote", "claim", "stake", "transfer", "approve",
                   "execute", "send", "create", "cancel", "sign", "buy", "sell",
                   "pay", "bridge", "delete", "update", "set_")


_CHAIN_NAMES = ("bsc", "bnb", "bnbchain", "bnb chain", "binance")
# Arguments that mean "the person asking". Deliberately exact rather than
# suffix-matched: `reserveAddress`, `tokenAddress` and `poolAddress` all end in
# "address" but name a contract, and filling one with the caller's wallet
# produced a live failure ("Reserve not found") that read as the agent's fault.
_ADDRESS_ARGS = ("useraddress", "walletaddress", "owneraddress", "payeraddress",
                 "accountaddress", "address", "account", "wallet", "owner", "user", "taker")


def _fill_argument(arg: str, prop: dict[str, Any], wallet: str | None):
    """One required argument, filled without guessing, or None.

    Three fillable shapes: an argument named like a user address takes the
    wallet the task already carries (public information the user gave us); an
    enum naming this chain takes that value; anything else is unknowable and
    disqualifies the tool.
    """
    low = arg.lower().replace("-", "").replace("_", "")
    # Exact match only. A suffix match reads "reserveAddress" as the caller.
    if wallet and low in _ADDRESS_ARGS:
        return wallet
    enum = prop.get("enum") or (prop.get("items") or {}).get("enum") or []
    match = next((v for v in enum if str(v).lower() in _CHAIN_NAMES), None)
    if match is not None:
        return [match] if prop.get("type") == "array" else match
    return None


def _safe_readonly_call(tool: dict[str, Any], wallet: str | None = None) -> dict[str, Any] | None:
    """Return arguments for a tool that is safe to call without being asked, or
    None. Safe means: read-only by name, no mutation words, and every required
    argument fillable without inventing anything (see _fill_argument).
    """
    raw = str(tool.get("name") or "")
    name = raw.lower().lstrip("_")
    stripped = name.split("_", 1)[1] if "_" in name and not name.startswith(_READONLY_PREFIXES) else name
    if any(word in name for word in _MUTATION_WORDS):
        return None
    if not (name.startswith(_READONLY_PREFIXES) or stripped.startswith(_READONLY_PREFIXES)):
        return None
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    args: dict[str, Any] = {}
    for arg in schema.get("required") or []:
        value = _fill_argument(arg, properties.get(arg) or {}, wallet)
        if value is None:
            return None
        args[arg] = value
    return args


def _is_agent_card(url: str) -> bool:
    low = url.split("?")[0].lower().rstrip("/")
    return "/.well-known/" in low or low.endswith("agent-card.json") or low.endswith("agent.json") or low.endswith("/card")


async def resolve_a2a_endpoint(client: httpx.AsyncClient, url: str, token_id: int | None = None) -> str:
    """Follow an A2A agent card to the JSON-RPC endpoint it advertises.

    Registrations overwhelmingly point at /.well-known/agent-card.json, which
    describes the agent rather than being something you can call — posting
    JSON-RPC at it just returns 404. The card names the real endpoint in `url`.
    Returned unchanged when the URL is already an endpoint.
    """
    url = substitute_agent_id(url, token_id)
    if not _is_agent_card(url):
        return url
    response = await client.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    _guard_response(response)
    card = _sse_or_json(response.text)
    if not isinstance(card, dict):
        raise AgentRejected("The agent card was not readable JSON.", reason="unreadable")
    # The card proves which agent answered, so a substituted id is verified
    # rather than assumed.
    if token_id is not None:
        claimed = str(card.get("agentTokenId") or card.get("tokenId") or token_id)
        if claimed != str(token_id):
            raise AgentRejected(f"The agent card belongs to a different agent (#{claimed}).", reason="upstream_error")

    target = card.get("url") or card.get("endpoint")
    if not target:
        for interface in (card.get("additionalInterfaces") or []):
            if isinstance(interface, dict) and str(interface.get("transport", "")).upper().startswith("JSONRPC"):
                target = interface.get("url")
                break
    if not target:
        # Some platforms say plainly that the registration has no service behind
        # it. That is a different fact from "unreachable" and is worth keeping.
        status = str(card.get("status") or "").upper()
        presence = str(card.get("presence") or "").lower()
        if status in ("UNBOUND", "INACTIVE", "DRAFT") or presence == "offline":
            raise AgentRejected(
                f"The hosting platform lists this agent as {status.lower() or presence} with no endpoint bound.",
                reason="unbound")
    if not target or _is_agent_card(str(target)):
        raise AgentRejected("The agent card names no callable endpoint.", reason="empty")
    # The card is third-party content, so its URL gets the same SSRF check as
    # the one that came from on-chain metadata.
    await _assert_public_https(str(target))
    return str(target)


async def _post(client: httpx.AsyncClient, url: str, payload: dict, session: str | None = None) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    response = await client.post(url, json=payload, headers=headers)
    _guard_response(response)
    return response


async def call_mcp(url: str, objective: str, wallet: str | None = None, action: str | None = None) -> dict[str, Any]:
    """initialize -> tools/list -> call a chat-like tool if present, else report tools."""
    await _assert_public_https(url)
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
        init = await _post(client, url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "agentdock", "version": "1.0"}}})
        session = init.headers.get("mcp-session-id") or init.headers.get("Mcp-Session-Id")
        _unwrap(_sse_or_json(init.text), "initialize")
        listed = await _post(client, url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
        tools = _unwrap(_sse_or_json(listed.text), "tools/list").get("tools") or []
        names = [t.get("name") for t in tools]
        # An explicitly chosen action wins: the visitor picked it by name, and it
        # was validated against this agent's own tool list before we got here.
        if action:
            chosen = next((t for t in tools if t.get("name") == action), None)
            if not chosen:
                raise AgentRejected(f"This agent no longer declares {action}.", reason="upstream_error")
            args = _safe_readonly_call(chosen, wallet)
            if args is None:
                raise AgentRejected(f"{action} is not something AgentDock can run on your behalf.", reason="upstream_error")
            called = await _post(client, url, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": action, "arguments": args}}, session)
            result = _unwrap(_sse_or_json(called.text), f"{action} tool")
            text = "\n".join(c.get("text", "") for c in (result.get("content") or []) if c.get("type") == "text").strip()
            if result.get("isError"):
                raise AgentRejected(f"The agent's {action} tool reported an error: {text or 'no detail given'}", reason="upstream_error")
            if not text:
                text = json.dumps(result)[:2000]
            if text.strip() in ("{}", "[]", "null", ""):
                raise AgentRejected(f"The agent's {action} tool returned an empty answer.", reason="empty")
            return {"transport": "mcp", "tool": action, "tools": names, "output": text[:4000]}

        chat = next((t for t in tools if t.get("name") in ("chat", "ask", "message", "query", "prompt")), None)
        if chat:
            arg_key = next(iter((chat.get("inputSchema") or {}).get("properties") or {"message": {}}), "message")
            called = await _post(client, url, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": chat["name"], "arguments": {arg_key: objective}}}, session)
            result = _unwrap(_sse_or_json(called.text), f"{chat['name']} tool")
            content = result.get("content") or []
            text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text").strip()
            # MCP reports a tool that ran and failed inside a successful
            # envelope, so this flag is the only signal that the text below is
            # an error message rather than an answer.
            if result.get("isError"):
                raise AgentRejected(f"The agent's {chat['name']} tool reported an error: {text or 'no detail given'}", reason="upstream_error")
            if not text:
                text = json.dumps(result)[:2000]
            if not text.strip() or text.strip() in ("{}", "[]", "null"):
                raise AgentRejected(f"The agent's {chat['name']} tool returned an empty answer.", reason="empty")
            return {"transport": "mcp", "tool": chat["name"], "tools": names, "output": text[:4000]}
        # No conversational tool. Before falling back to a listing, call the
        # tools that are safe to call unasked — read-only by name, and needing
        # no argument we would have to invent. Their live output is a far
        # better answer than a menu, and it is what the agent actually does.
        outputs = []
        # With a wallet in hand, the personalised tools are the interesting
        # ones: "your health factor" beats "the protocol description".
        candidates = [(tool, _safe_readonly_call(tool, wallet)) for tool in tools]
        candidates = [(tool, args) for tool, args in candidates if args is not None]
        candidates.sort(key=lambda pair: 0 if wallet and wallet in pair[1].values() else 1)
        for tool, args in candidates:
            try:
                called = await _post(client, url, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                    "params": {"name": tool["name"], "arguments": args}}, session)
                result = _unwrap(_sse_or_json(called.text), f"{tool['name']} tool")
                if result.get("isError"):
                    continue
                text = "\n".join(c.get("text", "") for c in (result.get("content") or []) if c.get("type") == "text").strip()
                if text and text not in ("{}", "[]", "null"):
                    outputs.append(f"── {tool['name']}\n{text[:1600]}")
            except (AgentRejected, AgentPaymentRequired):
                continue
            if len(outputs) >= 2:
                break
        if outputs:
            return {"transport": "mcp", "tool": "readonly", "tools": names, "output": "\n\n".join(outputs)[:4000]}
        summary = "This agent exposes the following live tools:\n" + "\n".join(
            f"• {t.get('name')}: {str(t.get('description') or '')[:100]}" for t in tools[:20]) if tools else "The agent responded but declared no callable tools."
        return {"transport": "mcp", "tools": names, "output": summary}


def _a2a_text(result: dict[str, Any]) -> str:
    """Collect the text an A2A reply carries, whichever shape it arrived in.

    A2A answers with either a Message (`parts`) or a Task, and a Task may put its
    text in `status.message`, in `artifacts`, or both.
    """
    def _parts(holder: Any) -> list[str]:
        if not isinstance(holder, dict):
            return []
        return [p.get("text", "") for p in (holder.get("parts") or [])
                if isinstance(p, dict) and (p.get("kind") == "text" or "text" in p)]

    found = _parts(result) + _parts(result.get("message"))
    found += _parts((result.get("status") or {}).get("message") if isinstance(result.get("status"), dict) else None)
    for artifact in (result.get("artifacts") or []):
        found += _parts(artifact)
    return "\n".join(p for p in found if p).strip()


async def call_a2a(url: str, objective: str, token_id: int | None = None) -> dict[str, Any]:
    await _assert_public_https(substitute_agent_id(url, token_id))
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT, follow_redirects=False) as client:
        target = await resolve_a2a_endpoint(client, url, token_id)
        response = await _post(client, target, {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {
            "message": {"role": "user", "parts": [{"kind": "text", "text": objective}], "messageId": "agentdock-1"}}})
        result = _unwrap(_sse_or_json(response.text), "message/send", tolerate_bare=True)
        text = _a2a_text(result)
        # A Task can complete the JSON-RPC call successfully while reporting that
        # the work itself did not succeed.
        state = ((result.get("status") or {}) if isinstance(result.get("status"), dict) else {}).get("state")
        if state in ("failed", "rejected", "canceled", "cancelled"):
            raise AgentRejected(f"The agent ended the task as {state}: {text or 'no reason given'}", reason="upstream_error")
        if not text:
            text = json.dumps(result)[:2000]
        if text.strip() in ("{}", "[]", "null", ""):
            raise AgentRejected("The agent returned an empty answer.", reason="empty")
        return {"transport": "a2a", "output": text[:4000]}


async def probe_endpoint(kind: str, url: str, token_id: int | None = None) -> tuple[str, str]:
    """Bounded wrapper around _probe: a probe that hangs is a dead endpoint."""
    try:
        return await asyncio.wait_for(_probe(kind, url, token_id), timeout=PROBE_WALL_CLOCK)
    except (asyncio.TimeoutError, TimeoutError):
        return "dead", f"Endpoint did not answer within {int(PROBE_WALL_CLOCK)}s"


async def _probe(kind: str, url: str, token_id: int | None = None) -> tuple[str, str]:
    """Check whether an endpoint can actually be called, returning (status, note).

    status is one of live | auth | payment | dead | error. Only "live" earns the
    Activate button: an endpoint published in on-chain metadata proves only that
    somebody wrote a URL there, and roughly a third of them turn out to be
    offline, credential-gated or paid.

    Neither probe asks the agent to think. MCP gets `initialize` + nothing else.
    A2A gets a read-only `tasks/get` for an id that cannot exist — a compliant
    server answers "task not found", which proves it is reachable and did not
    turn us away for credentials, without spending the operator's inference
    budget on a liveness check.
    """
    try:
        await _assert_public_https(substitute_agent_id(url, token_id))
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=False) as client:
            if kind == "mcp":
                url = substitute_agent_id(url, token_id)
                init = await _post(client, url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "agentdock", "version": "1.0"}}})
                _unwrap(_sse_or_json(init.text), "initialize")
                return "live", "MCP initialize succeeded"

            target = await resolve_a2a_endpoint(client, url, token_id)
            response = await _post(client, target, {"jsonrpc": "2.0", "id": 1, "method": "tasks/get",
                "params": {"id": "agentdock-liveness-probe"}})
            envelope = _sse_or_json(response.text)
            if envelope is None:
                return "error", "Endpoint did not answer with JSON"
            error = envelope.get("error")
            if not isinstance(error, dict):
                return "live", "A2A responded"
            message = str(error.get("message") or "")
            code = error.get("code")
            if _looks_like_auth(f"{code} {message}"):
                return "auth", message or "credential required"
            if code == -32001 or "not found" in message.lower():
                # The server looked the task up for us and it simply does not
                # exist. That is proof it would accept a real call.
                return "live", "A2A reachable (probe task not found, as expected)"
            # It rejected the request itself, not the task — so reachable is not
            # yet callable. One shared endpoint served 180 registrations and
            # answered every lookup, while refusing each actual call with "which
            # agent?". The only way to tell those apart is to make the call the
            # run path would make, so the verdict matches what the user gets.
            probe_body = {"jsonrpc": "2.0", "id": 2, "method": "message/send", "params": {
                "message": {"role": "user", "parts": [{"kind": "text", "text": PROBE_MESSAGE}], "messageId": "agentdock-probe"}}}
            send = await _post(client, target, probe_body)
            envelope = _sse_or_json(send.text) or {}
            reply_error = envelope.get("error") if isinstance(envelope.get("error"), dict) else None
            reply_message = str((reply_error or {}).get("message") or "")

            # The endpoint asked for the agent's id in the path. Take it at its word,
            # once, rather than recording "faulty" for something addressable.
            if reply_error and token_id is not None and _asks_for_agent_id(reply_message):
                send = await _post(client, f"{target.rstrip('/')}/{token_id}", probe_body)
                envelope = _sse_or_json(send.text) or {}
                reply_error = envelope.get("error") if isinstance(envelope.get("error"), dict) else None
                reply_message = str((reply_error or {}).get("message") or "")

            if reply_error and _looks_unbound(reply_message):
                return "unbound", reply_message
            _unwrap(envelope, "message/send", tolerate_bare=True)
            return "live", "A2A answered a probe message"
    except AgentPaymentRequired:
        return "payment", "Endpoint answers 402 — charges through its own x402 flow"
    except AgentRejected as exc:
        return {"auth": "auth", "unbound": "unbound"}.get(exc.reason, "error"), str(exc)
    except AgentCallError as exc:
        return "dead", str(exc)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return "dead", f"{type(exc).__name__}: {exc}"


async def fetch_capabilities(kind: str, url: str, token_id: int | None = None) -> list[dict[str, str]]:
    """What this agent declares it can do, in its own words.

    Only called for endpoints that already probed live — a handful — so the cost
    is negligible. Two uses, both of which need the agent's real vocabulary
    rather than ours: a visitor deciding between agents can see what each one
    actually offers, and the hire form can suggest an opening request instead of
    handing a newcomer an empty box.
    """
    try:
        if kind != "mcp":
            return []
        target = substitute_agent_id(url, token_id)
        await _assert_public_https(target)
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=False) as client:
            init = await _post(client, target, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "agentdock", "version": "1.0"}}})
            session = init.headers.get("mcp-session-id")
            listed = await _post(client, target, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
            tools = _unwrap(_sse_or_json(listed.text), "tools/list").get("tools") or []
        return [
            {"name": str(tool.get("name") or "")[:80],
             "description": str(tool.get("description") or "")[:200],
             # Kept so the safety gate can be re-run at call time against the
             # wallet the task carries, rather than trusted from a stored verdict.
             "input_schema": tool.get("inputSchema") or {}}
            for tool in tools if tool.get("name")
        ][:40]
    except (AgentCallError, AgentPaymentRequired, httpx.HTTPError, OSError, ValueError):
        return []


def runnable_actions(capabilities: list[dict[str, Any]], wallet: str | None = None) -> list[dict[str, Any]]:
    """The tools AgentDock may call on a visitor's behalf, with their arguments.

    The same gate the runtime uses, applied to stored capabilities: read-only by
    name, no mutation words, and every required argument fillable without
    inventing one. Returning the arguments too means the caller never has to
    reconstruct them — and never has to trust a name supplied by a browser.
    """
    actions = []
    for cap in capabilities:
        name = str(cap.get("name") or "")
        args = _safe_readonly_call({"name": name, "inputSchema": cap.get("input_schema") or {}}, wallet)
        if args is None:
            continue
        actions.append({"name": name, "description": " ".join((cap.get("description") or "").split())[:200], "args": args})
    return actions


def suggested_objectives(capabilities: list[dict[str, str]]) -> list[str]:
    """Openers a newcomer can click instead of composing prose.

    Every suggestion is a tool's own description, so we are never putting words
    in an agent's mouth — and every one passes the same mutation gate the
    runtime uses, so the marketplace never proposes borrowing, swapping or
    signing on the user's behalf.
    """
    seen: set[str] = set()
    out: list[str] = []
    for cap in capabilities:
        if _safe_readonly_call({"name": cap.get("name", ""), "inputSchema": {}}) is None:
            continue
        text = " ".join((cap.get("description") or "").split())
        if len(text) < 20 or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text[:180])
        if len(out) == 3:
            break
    return out


async def call_agent(kind: str, url: str, objective: str, token_id: int | None = None,
                     wallet: str | None = None, action: str | None = None) -> dict[str, Any]:
    if kind == "mcp":
        return await call_mcp(substitute_agent_id(url, token_id), objective, wallet, action)
    # A2A does carry the objective: message/send transmits it verbatim.
    return await call_a2a(url, objective, token_id)
