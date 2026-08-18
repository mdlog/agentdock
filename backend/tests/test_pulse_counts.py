"""The pulse under the search box is polled, not loaded once.

Its four figures are counted live from the catalogue, and two of them - the
registrations made today, and the endpoints ever called - had no index to count
from: each request scanned all 257,794 documents and took 950ms. That is
affordable once a minute and ruinous every few seconds, which is the cadence
that makes the number move while the sweep is calling endpoints.
"""

import os
import uuid

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MIDNIGHT = "2026-08-18T00:00:00+00:00"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def catalogue():
    """A throwaway catalogue carrying the production indexes."""
    import server

    url = os.environ.get("MONGO_URL")
    if not url:
        pytest.skip("MONGO_URL is not set")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    name = f"agentdock_test_{uuid.uuid4().hex[:12]}"
    collection = client[name].scan_agents
    await collection.insert_many([
        {"chain_id": 56, "token_id": 1, "created_at": "2026-08-18T09:00:00Z",
         "endpoint_status": "live", "activatable": True, "endpoint_primary": True},
        {"chain_id": 56, "token_id": 2, "created_at": "2026-08-14T09:00:00Z"},
        {"chain_id": 97, "token_id": 3, "created_at": "2026-08-18T09:00:00Z"},
    ])
    for spec in server.PULSE_INDEXES:
        await collection.create_index(spec["keys"], **spec.get("options", {}))
    yield collection
    await client.drop_database(name)


def _stages(plan):
    """Every stage name in a winning plan, however deeply nested."""
    if not isinstance(plan, dict):
        return []
    found = [plan["stage"]] if "stage" in plan else []
    for value in plan.values():
        if isinstance(value, dict):
            found += _stages(value)
        elif isinstance(value, list):
            for item in value:
                found += _stages(item)
    return found


@pytest.mark.anyio
async def test_no_pulse_figure_is_counted_by_scanning_the_catalogue(catalogue):
    import server

    for name, query in server.pulse_queries(56, MIDNIGHT).items():
        plan = (await catalogue.find(query).explain())["queryPlanner"]["winningPlan"]

        assert "COLLSCAN" not in _stages(plan), f"{name} scans the collection: {_stages(plan)}"


@pytest.mark.anyio
async def test_the_figures_still_count_the_right_agents(catalogue):
    """An index that changes the answer is not an optimisation."""
    import server

    queries = server.pulse_queries(56, MIDNIGHT)
    counts = {name: await catalogue.count_documents(q) for name, q in queries.items()}

    assert counts == {"catalogue_total": 2, "registered_today": 1,
                      "endpoints_verified": 1, "agents_live": 1}
