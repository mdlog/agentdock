"""The catalogue grows faster than the sweep that verifies it.

Between 16 and 18 August the marketplace ingested 1,020 new registrations and
called 5 of their endpoints: the hourly sweep only looks at agents it already
knows are interesting - categorised, or already answering - so a registration
whose name matches no category was never called at all. 239,457 agents had
never been probed once. These tests pin the second sweep that fixes that, and
the boundary between the two.
"""

import os
import uuid

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

STALE_BEFORE = "2026-08-18T00:00:00+00:00"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def agents():
    """A throwaway database holding four agents, one per interesting state."""
    url = os.environ.get("MONGO_URL")
    if not url:
        pytest.skip("MONGO_URL is not set")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    name = f"agentdock_test_{uuid.uuid4().hex[:12]}"
    collection = client[name].scan_agents
    await collection.insert_many([
        # Never called. The backlog exists for these two.
        {"chain_id": 56, "token_id": 100, "categories": [], "created_at": "2026-08-17T00:00:00Z"},
        {"chain_id": 56, "token_id": 200, "categories": [], "created_at": "2026-08-18T00:00:00Z"},
        # Called, and answering. The hourly refresh keeps this one current.
        {"chain_id": 56, "token_id": 50, "categories": ["yield-optimisation"], "activatable": True,
         "endpoint_status": "live", "endpoint_checked_at": "2026-08-17T00:00:00+00:00"},
        # Called, and it errored. Deliberately left alone by both sweeps: 1,095
        # registrations share one URL that answers 405, and re-deriving that
        # same 405 twice a day is 1,095 pointless requests to one host.
        {"chain_id": 56, "token_id": 60, "categories": [], "endpoint_status": "error",
         "endpoint_checked_at": "2026-08-01T00:00:00+00:00"},
    ])
    yield collection
    await client.drop_database(name)


async def _selected(collection, scope):
    import server

    query, sort, _ = server.endpoint_scope(56, scope, STALE_BEFORE)
    cursor = collection.find(query, {"_id": 0, "token_id": 1})
    if sort:
        cursor = cursor.sort(sort)
    return [row["token_id"] for row in await cursor.to_list(50)]


@pytest.mark.anyio
async def test_the_backlog_takes_every_agent_nobody_has_ever_called(agents):
    assert sorted(await _selected(agents, "backlog")) == [100, 200]


@pytest.mark.anyio
async def test_the_backlog_starts_with_the_newest_registration(agents):
    """Newest first, so today's registrations are called within the hour
    instead of queueing behind a quarter of a million older ones."""
    assert await _selected(agents, "backlog") == [200, 100]


@pytest.mark.anyio
async def test_an_endpoint_that_already_errored_is_not_called_again(agents):
    assert 60 not in await _selected(agents, "backlog")
    assert 60 not in await _selected(agents, "refresh")


@pytest.mark.anyio
async def test_the_refresh_still_owns_the_verdicts_that_have_gone_stale(agents):
    assert 50 in await _selected(agents, "refresh")


def test_the_two_sweeps_record_under_different_sources():
    """Each pass writes a "running" flag its own loop checks before starting.
    Sharing one record would let a long backlog pass stall the hourly refresh."""
    import server

    backlog = server.endpoint_scope(56, "backlog", STALE_BEFORE)[2]
    refresh = server.endpoint_scope(56, "refresh", STALE_BEFORE)[2]

    assert backlog != refresh


# --- the loop that works through it ------------------------------------------


class _StopLoop(Exception):
    """Raised from the patched sleep to end an otherwise endless loop."""


async def _run_loop(monkeypatch, passes):
    import server

    remaining = list(passes)
    delays: list[float] = []

    async def _pass(chain_id, limit=600, scope="refresh"):
        assert scope == "backlog"
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def _sleep(seconds):
        delays.append(seconds)
        if not remaining:
            raise _StopLoop

    monkeypatch.setattr(server, "enrich_endpoints", _pass)
    monkeypatch.setattr(server.asyncio, "sleep", _sleep)
    with pytest.raises(_StopLoop):
        await server._backlog_loop(batch=10, pause_seconds=7, idle_seconds=900)
    return delays


@pytest.mark.anyio
async def test_the_loop_goes_quiet_once_every_agent_has_been_called(monkeypatch):
    """An exhausted backlog must stop asking. Without this the sweep would keep
    running the same empty query every few seconds for as long as the app is up."""
    delays = await _run_loop(monkeypatch, [{"checked": 10, "activatable": 1},
                                           {"checked": 0, "activatable": 0}])

    assert delays == [7, 900]


@pytest.mark.anyio
async def test_a_failed_pass_does_not_end_the_sweep(monkeypatch):
    """8004scan returns 502s. A loop that dies on one leaves the backlog frozen
    until someone notices and restarts the service."""
    delays = await _run_loop(monkeypatch, [RuntimeError("8004scan returned HTTP 502"),
                                           {"checked": 10, "activatable": 0}])

    assert len(delays) == 2


# --- a verdict is worth publishing the moment it is known --------------------


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Agents:
    def __init__(self, docs, log):
        self.docs, self.log = docs, log

    def find(self, *_a, **_kw):
        return _Cursor(sorted(self.docs, key=lambda d: -d["token_id"]))

    async def update_one(self, query, _update, **_kw):
        self.log.append(("write", query["token_id"]))


class _Runs:
    async def update_one(self, *_a, **_kw):
        return None

    async def find_one(self, *_a, **_kw):
        return None


@pytest.mark.anyio
async def test_each_verdict_is_recorded_before_the_next_agent_is_read(monkeypatch):
    """The sweep spends 0.34s per agent reading metadata, and most agents in the
    backlog publish no endpoint at all. Collecting those verdicts and writing
    them in one burst at the end left the public count frozen for 135 seconds
    and then jumping by 400 — measured on the deployment, twice."""
    import server

    log: list[tuple[str, int]] = []
    agents = _Agents([{"chain_id": 56, "token_id": t, "name": "", "description": ""} for t in (1, 2, 3)], log)

    class _Db:
        scan_agents = agents
        sync_runs = _Runs()

    class _Client:
        async def agent_detail(self, _chain_id, token_id):
            log.append(("read", token_id))
            return {"token_id": token_id}

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(server, "db", _Db())
    monkeypatch.setattr(server, "Scan8004Client", lambda: _Client())
    monkeypatch.setattr(server.agent_client, "pick_endpoint", lambda _detail: None)
    monkeypatch.setattr(server, "mark_endpoint_groups", lambda chain_id=56: {"services": 0, "registrations": 0})
    monkeypatch.setattr(server.asyncio, "sleep", _no_sleep)

    result = await server.enrich_endpoints(56, limit=3, scope="backlog")

    assert log == [("read", 3), ("write", 3), ("read", 2), ("write", 2), ("read", 1), ("write", 1)]
    assert result["checked"] == 3
