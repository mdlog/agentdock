"""An agent that refuses must never be reported as an agent that answered.

Both supported transports are JSON-RPC 2.0, so a refusal arrives as a perfectly
ordinary HTTP 200 carrying an `error` member — and MCP reports tool failures a
third way again, inside `result.isError`. Reading only `result` turns every one
of those into the agent's "output": the marketplace displayed
`{"error": {"code": "UNAUTHORIZED"}}` as a completed result. These tests pin the
distinction the classifier has to draw.
"""

import json

import httpx
import pytest

import agent_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _response(payload, status=200, headers=None):
    return httpx.Response(
        status,
        content=json.dumps(payload).encode() if not isinstance(payload, (bytes, str)) else payload,
        headers={"content-type": "application/json", **(headers or {})},
        request=httpx.Request("POST", "https://agent.example/rpc"),
    )


class _ScriptedClient:
    """Answers each POST with the next queued response."""

    def __init__(self, queue):
        self.queue = list(queue)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, json=None, headers=None):  # noqa: A002 - httpx's own kwarg name
        self.sent.append({"method": "POST", "url": url, "body": json})
        return self.queue.pop(0)

    async def get(self, url, headers=None):
        self.sent.append({"method": "GET", "url": url})
        return self.queue.pop(0)


@pytest.fixture
def public_host(monkeypatch):
    """Skip DNS; these tests are about response classification, not SSRF."""
    async def _ok(_url):
        return None

    monkeypatch.setattr(agent_client, "_assert_public_https", _ok)


def _install(monkeypatch, queue):
    client = _ScriptedClient(queue)
    monkeypatch.setattr(agent_client.httpx, "AsyncClient", lambda **_kw: client)
    return client


# --- the reported bug: a JSON-RPC refusal became a result -------------------

@pytest.mark.anyio
async def test_a2a_jsonrpc_error_is_a_refusal_not_an_answer(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"}})])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://agent.example/rpc", "what do you do?")

    assert caught.value.reason == "auth"
    assert "Unauthorized" in str(caught.value)


@pytest.mark.anyio
async def test_mcp_jsonrpc_error_is_a_refusal_not_an_answer(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "server exploded"}})])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_mcp("https://agent.example/rpc", "hello")

    assert caught.value.reason == "upstream_error"
    assert "server exploded" in str(caught.value)


@pytest.mark.anyio
async def test_mcp_tool_error_flag_is_a_refusal(monkeypatch, public_host):
    """MCP reports tool failure inside a successful envelope, via result.isError."""
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "chat", "inputSchema": {"properties": {"message": {}}}}]}}),
        _response({"jsonrpc": "2.0", "id": 3, "result": {"isError": True, "content": [{"type": "text", "text": "rate limit exceeded"}]}}),
    ])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_mcp("https://agent.example/rpc", "hello")

    assert "rate limit exceeded" in str(caught.value)


# --- HTTP status was only ever checked for 402 ------------------------------

@pytest.mark.parametrize("status,reason", [(401, "auth"), (403, "auth"), (500, "upstream_error"), (404, "upstream_error")])
@pytest.mark.anyio
async def test_http_error_status_never_becomes_output(monkeypatch, public_host, status, reason):
    _install(monkeypatch, [_response({"detail": "nope"}, status=status)])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://agent.example/rpc", "hello")

    assert caught.value.reason == reason


@pytest.mark.anyio
async def test_402_still_routes_to_the_payment_flow(monkeypatch, public_host):
    _install(monkeypatch, [_response({"accepts": []}, status=402)])

    with pytest.raises(agent_client.AgentPaymentRequired):
        await agent_client.call_a2a("https://agent.example/rpc", "hello")


# --- empty and unreadable answers are not answers ---------------------------

@pytest.mark.anyio
async def test_unparseable_body_is_rejected(monkeypatch, public_host):
    _install(monkeypatch, [_response(b"<html>502 Bad Gateway</html>")])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://agent.example/rpc", "hello")

    assert caught.value.reason == "unreadable"


@pytest.mark.anyio
async def test_result_with_no_text_is_rejected(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "result": {}})])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://agent.example/rpc", "hello")

    assert caught.value.reason == "empty"


@pytest.mark.anyio
async def test_a2a_failed_task_state_is_a_refusal(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "result": {
        "id": "t1", "status": {"state": "failed", "message": {"parts": [{"kind": "text", "text": "upstream model unavailable"}]}}}})])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://agent.example/rpc", "hello")

    assert "upstream model unavailable" in str(caught.value)


# --- the good paths must keep working ---------------------------------------

@pytest.mark.anyio
async def test_a2a_real_answer_still_succeeds(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "result": {
        "role": "agent", "parts": [{"kind": "text", "text": "The current gas price on BNB Chain is 3 Gwei."}]}})])

    result = await agent_client.call_a2a("https://agent.example/rpc", "gas price?")

    assert result["transport"] == "a2a"
    assert "3 Gwei" in result["output"]


@pytest.mark.anyio
async def test_a2a_task_artifacts_are_read_as_output(monkeypatch, public_host):
    """A2A may answer with a Task carrying artifacts rather than a bare Message."""
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "result": {
        "id": "t1", "status": {"state": "completed"},
        "artifacts": [{"parts": [{"kind": "text", "text": "APY on Venus is 4.2%"}]}]}})])

    result = await agent_client.call_a2a("https://agent.example/rpc", "venus apy?")

    assert "4.2%" in result["output"]


@pytest.mark.anyio
async def test_a2a_tolerates_a_bare_message_without_the_envelope(monkeypatch, public_host):
    """Some registered agents answer the message object directly. That worked
    before the classifier existed and must keep working."""
    _install(monkeypatch, [_response({"role": "agent", "parts": [{"kind": "text", "text": "bare but valid"}]})])

    result = await agent_client.call_a2a("https://agent.example/rpc", "hello")

    assert "bare but valid" in result["output"]


@pytest.mark.anyio
async def test_mcp_chat_tool_answer_still_succeeds(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "chat", "inputSchema": {"properties": {"message": {}}}}]}}),
        _response({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "3 Gwei"}]}}),
    ])

    result = await agent_client.call_mcp("https://agent.example/rpc", "gas price?")

    assert result["output"] == "3 Gwei"
    assert result["tool"] == "chat"


@pytest.mark.anyio
async def test_mcp_without_a_chat_tool_reports_its_real_tools(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "swap_quote", "description": "Quote a swap"}]}}),
    ])

    result = await agent_client.call_mcp("https://agent.example/rpc", "hello")

    assert "swap_quote" in result["output"]


# --- probing: activatable has to mean "we called it and it worked" ----------

@pytest.mark.anyio
async def test_probe_reports_live_for_a_healthy_mcp_server(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}})])

    status, _note = await agent_client.probe_endpoint("mcp", "https://agent.example/rpc")

    assert status == "live"


@pytest.mark.anyio
async def test_probe_reports_auth_for_a_credentialled_endpoint(monkeypatch, public_host):
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"}})])

    status, note = await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert status == "auth"
    assert "Unauthorized" in note


@pytest.mark.anyio
async def test_probe_treats_task_not_found_as_live(monkeypatch, public_host):
    """The A2A probe is a read-only lookup for an id that cannot exist. A
    compliant server answering "not found" has proved it is reachable and let us
    in — without spending the agent's inference budget on a probe message."""
    _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "Task not found"}})])

    status, _note = await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert status == "live"


@pytest.mark.anyio
async def test_probe_sends_no_message_when_the_lookup_already_answers(monkeypatch, public_host):
    client = _install(monkeypatch, [_response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "Task not found"}})])

    await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert [p["body"]["method"] for p in client.sent] == ["tasks/get"]


@pytest.mark.anyio
async def test_probe_reports_payment_for_a_402_endpoint(monkeypatch, public_host):
    _install(monkeypatch, [_response({"accepts": []}, status=402)])

    status, _note = await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert status == "payment"


@pytest.mark.anyio
async def test_probe_reports_dead_when_the_host_is_unreachable(monkeypatch):
    async def _boom(_url):
        raise agent_client.AgentCallError("Agent endpoint host could not be resolved")

    monkeypatch.setattr(agent_client, "_assert_public_https", _boom)

    status, note = await agent_client.probe_endpoint("mcp", "https://gone.example/rpc")

    assert status == "dead"
    assert "resolved" in note


@pytest.mark.anyio
async def test_probe_reports_dead_on_connect_failure(monkeypatch, public_host):
    class _Broken:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, *_a, **_kw):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(agent_client.httpx, "AsyncClient", lambda **_kw: _Broken())

    status, _note = await agent_client.probe_endpoint("mcp", "https://gone.example/rpc")

    assert status == "dead"


# --- an agent card is a description, not an endpoint ------------------------

CARD = {"name": "BORT Agent", "url": "https://api.example/api/a2a", "preferredTransport": "JSONRPC"}


@pytest.mark.anyio
async def test_a2a_follows_an_agent_card_to_the_real_endpoint(monkeypatch, public_host):
    """The most common A2A registration points at /.well-known/agent-card.json.
    Posting JSON-RPC at that static file just 404s — the card has to be read."""
    client = _install(monkeypatch, [
        _response(CARD),
        _response({"jsonrpc": "2.0", "id": 1, "result": {"parts": [{"kind": "text", "text": "BORT here"}]}}),
    ])

    result = await agent_client.call_a2a("https://api.example/.well-known/agent-card.json", "hi")

    assert "BORT here" in result["output"]
    assert [(c["method"], c["url"]) for c in client.sent] == [
        ("GET", "https://api.example/.well-known/agent-card.json"),
        ("POST", "https://api.example/api/a2a"),
    ]


@pytest.mark.anyio
async def test_probe_follows_an_agent_card_before_judging_it(monkeypatch, public_host):
    _install(monkeypatch, [
        _response(CARD),
        _response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "Task not found"}}),
    ])

    status, _note = await agent_client.probe_endpoint("a2a", "https://api.example/.well-known/agent-card.json")

    assert status == "live"


@pytest.mark.anyio
async def test_card_endpoint_gets_the_same_ssrf_check(monkeypatch):
    """The card is third-party content: it must not be able to point us inward."""
    seen = []

    async def _check(url):
        seen.append(url)
        if "internal" in url:
            raise agent_client.AgentCallError("Agent endpoint resolves to a non-public address")

    monkeypatch.setattr(agent_client, "_assert_public_https", _check)
    _install(monkeypatch, [_response({"name": "evil", "url": "https://internal.local/admin"})])

    with pytest.raises(agent_client.AgentCallError):
        await agent_client.call_a2a("https://api.example/.well-known/agent-card.json", "hi")

    assert "https://internal.local/admin" in seen


@pytest.mark.anyio
async def test_card_without_an_endpoint_is_rejected(monkeypatch, public_host):
    _install(monkeypatch, [_response({"name": "incomplete", "description": "no url field"})])

    with pytest.raises(agent_client.AgentRejected):
        await agent_client.call_a2a("https://api.example/.well-known/agent-card.json", "hi")


@pytest.mark.anyio
async def test_card_additional_interface_is_used_when_url_is_absent(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"name": "iface only", "additionalInterfaces": [
            {"transport": "GRPC", "url": "https://api.example/grpc"},
            {"transport": "JSONRPC", "url": "https://api.example/rpc"}]}),
        _response({"jsonrpc": "2.0", "id": 1, "result": {"parts": [{"kind": "text", "text": "ok"}]}}),
    ])

    result = await agent_client.call_a2a("https://api.example/.well-known/agent-card.json", "hi")

    assert result["output"] == "ok"


@pytest.mark.anyio
async def test_probe_gives_up_on_a_hanging_endpoint(monkeypatch, public_host):
    """DNS is not covered by httpx timeouts, so the probe carries its own ceiling."""
    monkeypatch.setattr(agent_client, "PROBE_WALL_CLOCK", 0.05)

    async def _hang(_url):
        await __import__("asyncio").sleep(5)

    monkeypatch.setattr(agent_client, "_assert_public_https", _hang)

    status, note = await agent_client.probe_endpoint("mcp", "https://slow.example/mcp")

    assert status == "dead"
    assert "did not answer" in note


@pytest.mark.anyio
async def test_probe_falls_back_to_a_message_when_the_lookup_is_rejected(monkeypatch, public_host):
    """An endpoint may not implement tasks/get at all. That says nothing about
    whether it can be called, so the probe asks the way the run path would."""
    client = _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unsupported method: tasks/get"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"parts": [{"kind": "text", "text": "pong"}]}}),
    ])

    status, _note = await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert status == "live"
    assert [p["body"]["method"] for p in client.sent] == ["tasks/get", "message/send"]


@pytest.mark.anyio
async def test_reachable_is_not_callable(monkeypatch, public_host):
    """The real case this rule exists for: one shared endpoint backed 180
    registrations, answered every lookup, and refused each actual call with
    "which agent?". Reachable must not be recorded as activatable."""
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unsupported method: tasks/get"}}),
        _response({"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "a valid agent tokenId is required"}}),
    ])

    status, note = await agent_client.probe_endpoint("a2a", "https://agent.example/rpc")

    assert status == "error"
    assert "tokenId" in note


# --- a registered URL may be a template, and a card may say "not deployed" ----

def test_placeholder_is_substituted_with_the_agents_own_id():
    url = "https://platform.example/api/v1/a2a/agents/{agentId}/card"

    assert agent_client.substitute_agent_id(url, 255133) == "https://platform.example/api/v1/a2a/agents/255133/card"


def test_url_without_a_placeholder_is_untouched():
    url = "https://agent.example/rpc"

    assert agent_client.substitute_agent_id(url, 255133) == url


@pytest.mark.anyio
async def test_card_identity_is_verified_before_the_substitution_is_trusted(monkeypatch, public_host):
    """Substituting an id is only safe because the card says whose it is."""
    _install(monkeypatch, [_response({"agentTokenId": "999", "name": "Someone Else", "url": "https://agent.example/rpc"})])

    with pytest.raises(agent_client.AgentRejected) as caught:
        await agent_client.call_a2a("https://platform.example/api/v1/a2a/agents/{agentId}/card", "hi", 255133)

    assert "different agent" in str(caught.value)


@pytest.mark.anyio
async def test_platform_saying_unbound_is_not_reported_as_unreachable(monkeypatch, public_host):
    """The real Termix shape: the card resolves, and states plainly that no
    service is attached. That is a different fact from a dead host."""
    _install(monkeypatch, [_response({
        "agentTokenId": "255133", "name": "Grid-v3.agent", "endpoint": None,
        "status": "UNBOUND", "presence": "offline", "skills": []})])

    status, note = await agent_client.probe_endpoint(
        "a2a", "https://platform.example/api/v1/a2a/agents/{agentId}/card", 255133)

    assert status == "unbound"
    assert "unbound" in note.lower()


@pytest.mark.anyio
async def test_card_endpoint_field_is_used_when_present(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"agentTokenId": "42", "name": "Bound", "endpoint": "https://agent.example/rpc", "status": "BOUND"}),
        _response({"jsonrpc": "2.0", "id": 1, "result": {"parts": [{"kind": "text", "text": "hello"}]}}),
    ])

    result = await agent_client.call_a2a("https://platform.example/api/v1/a2a/agents/{agentId}/card", "hi", 42)

    assert "hello" in result["output"]


@pytest.mark.anyio
async def test_shared_endpoint_asking_for_an_id_is_retried_at_the_path_it_named(monkeypatch, public_host):
    """The real BORT shape: one endpoint backs many registrations and answers
    "a valid agent tokenId is required (path /api/a2a/:agentId)". Following the
    convention it stated turns "faulty" into the operator's real answer."""
    client = _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unsupported method: tasks/get"}}),
        _response({"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "a valid agent tokenId is required (path /api/a2a/:agentId)"}}),
        _response({"jsonrpc": "2.0", "id": 2, "error": {"code": -32040, "message": "agent 153799 is not open to inbound A2A calls"}}),
    ])

    status, note = await agent_client.probe_endpoint("a2a", "https://api.example/api/a2a", 153799)

    assert status == "unbound"
    assert "not open to inbound" in note
    assert client.sent[-1]["url"] == "https://api.example/api/a2a/153799"


@pytest.mark.anyio
async def test_agent_reachable_at_the_named_path_is_live(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unsupported method"}}),
        _response({"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "a valid agent tokenId is required"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"parts": [{"kind": "text", "text": "I am agent 7"}]}}),
    ])

    status, _note = await agent_client.probe_endpoint("a2a", "https://api.example/api/a2a", 7)

    assert status == "live"


# --- when there is no chat tool, safe read-only tools ARE the answer ---------

def test_safe_call_zero_arg_read_tool():
    assert agent_client._safe_readonly_call({"name": "topaz_get_protocol_stats", "inputSchema": {"required": []}}) == {}


def test_safe_call_fills_a_chain_enum():
    tool = {"name": "getVaultsWithChains", "inputSchema": {
        "required": ["chainNames"],
        "properties": {"chainNames": {"type": "array", "items": {"enum": ["ethereum", "bsc", "base"]}}}}}

    assert agent_client._safe_readonly_call(tool) == {"chainNames": ["bsc"]}


@pytest.mark.parametrize("name", ["borrow", "topaz_build_swap_calldata", "get_and_execute", "claimRewards", "setConfig"])
def test_mutating_tools_are_never_called_unasked(name):
    assert agent_client._safe_readonly_call({"name": name, "inputSchema": {"required": []}}) is None


def test_tools_needing_unknowable_args_are_skipped():
    tool = {"name": "getBorrowBalance", "inputSchema": {"required": ["chainName", "userAddress"]}}

    assert agent_client._safe_readonly_call(tool) is None


@pytest.mark.anyio
async def test_mcp_without_chat_calls_safe_tools_and_returns_their_output(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [
            {"name": "borrow", "inputSchema": {"required": []}},
            {"name": "get_protocol_stats", "inputSchema": {"required": []}},
        ]}}),
        _response({"jsonrpc": "2.0", "id": 4, "result": {"content": [{"type": "text", "text": '{"tvlUsd": "1117243"}'}]}}),
    ])

    result = await agent_client.call_mcp("https://agent.example/rpc", "yield overview?")

    assert "1117243" in result["output"]
    assert result["tool"] == "readonly"


@pytest.mark.anyio
async def test_mcp_falls_back_to_the_listing_when_nothing_is_safe(monkeypatch, public_host):
    _install(monkeypatch, [
        _response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}),
        _response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [
            {"name": "borrow", "description": "Borrow a token", "inputSchema": {"required": ["amount"]}},
        ]}}),
    ])

    result = await agent_client.call_mcp("https://agent.example/rpc", "hello")

    assert "borrow" in result["output"]
    assert "live tools" in result["output"]


# --- the connected wallet may answer for its own public positions ------------

def test_address_argument_is_filled_from_the_task_wallet():
    tool = {"name": "getUserHealthIndicators", "inputSchema": {
        "required": ["chainNames", "userAddress"],
        "properties": {"chainNames": {"type": "array", "items": {"enum": ["ethereum", "bnbchain"]}},
                        "userAddress": {"type": "string"}}}}

    args = agent_client._safe_readonly_call(tool, wallet="0x" + "a" * 40)

    assert args == {"chainNames": ["bnbchain"], "userAddress": "0x" + "a" * 40}


def test_address_tools_are_skipped_when_no_wallet_is_connected():
    tool = {"name": "getUserHealthIndicators", "inputSchema": {
        "required": ["userAddress"], "properties": {"userAddress": {"type": "string"}}}}

    assert agent_client._safe_readonly_call(tool, wallet=None) is None


def test_string_chain_enum_is_filled_without_an_array():
    tool = {"name": "getReserveOverview", "inputSchema": {
        "required": ["chainName"], "properties": {"chainName": {"type": "string", "enum": ["ethereum", "bsc"]}}}}

    assert agent_client._safe_readonly_call(tool) == {"chainName": "bsc"}


def test_wallet_never_leaks_into_a_mutating_tool():
    tool = {"name": "withdrawAll", "inputSchema": {
        "required": ["userAddress"], "properties": {"userAddress": {"type": "string"}}}}

    assert agent_client._safe_readonly_call(tool, wallet="0x" + "a" * 40) is None


# --- openers must come from the agent, and must never propose a mutation -----

def test_suggestions_use_the_agents_own_words():
    caps = [{"name": "get_status", "description": "Current picture: health factor, risk band and stress curve."}]

    assert agent_client.suggested_objectives(caps) == ["Current picture: health factor, risk band and stress curve."]


def test_a_mutating_tool_is_never_suggested():
    """The marketplace must not propose borrowing or signing on a user's behalf."""
    caps = [
        {"name": "borrow", "description": "Borrow a token from the lending protocol on a chain."},
        {"name": "build_swap_calldata", "description": "Build wallet-ready swap calldata to sign and broadcast."},
        {"name": "get_pool_stats", "description": "Get top pools sorted by TVL, volume, fees, or APR."},
    ]

    assert agent_client.suggested_objectives(caps) == ["Get top pools sorted by TVL, volume, fees, or APR."]


def test_at_most_three_suggestions_and_no_duplicates():
    caps = [{"name": f"get_thing_{i}", "description": "Get the same overview of everything available."} for i in range(6)]
    caps += [{"name": "list_pools", "description": "List every pool with its current liquidity depth."}]

    suggestions = agent_client.suggested_objectives(caps)

    assert len(suggestions) == 2
    assert len(set(suggestions)) == 2


def test_useless_descriptions_are_skipped():
    """A tool described as "get" gives a newcomer nothing to click."""
    caps = [{"name": "get_x", "description": "Get."}, {"name": "get_y", "description": ""}]

    assert agent_client.suggested_objectives(caps) == []


def test_an_agent_with_no_capabilities_offers_nothing_rather_than_inventing():
    assert agent_client.suggested_objectives([]) == []


@pytest.mark.parametrize("arg", ["reserveAddress", "tokenAddress", "poolAddress", "contractAddress"])
def test_a_contract_address_argument_is_not_the_callers_wallet(arg):
    """Filling reserveAddress with the caller's wallet produced a live
    "Reserve not found" that read as the agent failing, not us."""
    tool = {"name": "getReserveHumanized", "inputSchema": {
        "required": [arg], "properties": {arg: {"type": "string"}}}}

    assert agent_client._safe_readonly_call(tool, wallet="0x" + "a" * 40) is None


@pytest.mark.parametrize("arg", ["userAddress", "user_address", "walletAddress", "account", "owner", "taker"])
def test_arguments_that_mean_the_caller_are_filled(arg):
    tool = {"name": "getUserPositions", "inputSchema": {
        "required": [arg], "properties": {arg: {"type": "string"}}}}

    assert agent_client._safe_readonly_call(tool, wallet="0x" + "a" * 40) == {arg: "0x" + "a" * 40}


# --- a live tool list outranks the name an agent filed itself under ----------

from scan8004 import derive_categories_from_capabilities, effective_categories


def test_tools_classify_an_agent_its_name_misfiled():
    """The real case: "Fly Marketing Agent" matched yield optimisation because
    its blurb says "optimise". Its three tools are about shop marketing."""
    caps = [{"name": "generate_marketing_plan", "description": "Build a marketing plan for a shop"},
            {"name": "check_geo_ranking", "description": "Check a shop's local ranking"}]

    categories, source = effective_categories("Fly Marketing Agent", "AI that optimises your shop", caps)

    assert categories == []
    assert source == "capabilities"


def test_a_lending_position_is_not_an_lp_range():
    """"position" means an LP range in a DEX and a loan in a lending protocol;
    matching it filed Aave and the Lending Guardian as rebalancing agents."""
    lending = [{"name": "getUserHealthIndicators", "description": "Health factor and borrow position for a user"}]

    assert derive_categories_from_capabilities(lending) == ["health-factor"]


def test_concentrated_liquidity_tools_are_rebalancing():
    clm = [{"name": "topaz_get_cl_position_by_id", "description": "Concentrated liquidity position with tick range"}]

    assert derive_categories_from_capabilities(clm) == ["rebalancing"]


def test_an_unreadable_tool_list_leaves_the_metadata_verdict_alone():
    """An A2A agent publishes no tools/list. Erasing its category because of a
    silence we caused would be our failure recorded as its absence."""
    categories, source = effective_categories("BNB LP Range Rebalancer", "Rebalances LP ranges on PancakeSwap", [])

    assert categories == ["rebalancing"]
    assert source == "metadata"


def test_tools_that_say_nothing_recognisable_yield_no_category():
    assert derive_categories_from_capabilities([{"name": "ping", "description": "Returns pong"}]) == []
