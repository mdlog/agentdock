"""Onchain 8004scan integration tests: status, projection, filters, persistence safety."""

import os
import sys
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


if "/app/backend" not in sys.path:
    sys.path.append("/app/backend")

from scan8004 import Scan8004Error, Scan8004Client, sync_bsc_mainnet, sync_feedbacks


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _load_backend_env() -> dict:
    env_file = Path("/app/backend/.env")
    return dotenv_values(env_file)


def _contains_forbidden_keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            lowered = str(key).lower()
            if "api_key" in lowered or "scan8004" in lowered and "key" in lowered:
                return True
            if _contains_forbidden_keys(inner):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_keys(item) for item in value)
    return False


@pytest.fixture(scope="session")
def api_base_url() -> str:
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def mongo_db():
    env = _load_backend_env()
    mongo_url = env.get("MONGO_URL")
    db_name = env.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL or DB_NAME missing in backend/.env")
    client = MongoClient(mongo_url)
    db = client[db_name]
    yield db
    client.close()


# 8004scan status endpoint tests
def test_scan_status_success_fields(api_client: requests.Session, api_base_url: str):
    data = None
    for _ in range(30):
        response = api_client.get(f"{api_base_url}/api/integrations/8004scan/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        if data.get("status") == "success":
            break
        time.sleep(2)

    assert data is not None
    assert data["status"] == "success"
    assert data["source"] == "8004scan"
    assert data["chain_id"] == 56
    assert data["is_testnet"] is False
    assert data["imported"] == 100
    assert data["sample_limit"] == 100
    assert data["available_total"] > 100


def test_scan_status_no_api_key_leak(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/integrations/8004scan/status", timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert _contains_forbidden_keys(data) is False
    serialized = str(data).lower()
    assert "x-api-key" not in serialized
    assert "scan8004_api_key" not in serialized


# Onchain list/projection tests
def test_onchain_agents_public_projection_100_items(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents", timeout=40)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 100
    assert len(data["items"]) == 100
    assert data["source"] == "8004scan"
    assert data["chain_id"] == 56
    assert data["is_testnet"] is False


def test_onchain_agents_no_raw_payload_or_keys(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents", timeout=40)
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["chain_id"] == 56
        assert item["source"] == "8004scan"
        assert "raw_8004scan" not in item
        assert "api_key" not in " ".join(item.keys()).lower()


# Backend filter and sorting tests
def test_onchain_filters_search_protocol_x402_verified_and_sort(api_client: requests.Session, api_base_url: str):
    all_data = api_client.get(f"{api_base_url}/api/onchain/agents", timeout=40).json()["items"]
    assert len(all_data) == 100

    protocol = None
    for row in all_data:
        if row.get("supported_protocols"):
            protocol = row["supported_protocols"][0]
            break
    if not protocol:
        pytest.skip("No protocol found in sampled dataset")

    search_term = all_data[0]["name"].split(" ")[0]
    response = api_client.get(
        f"{api_base_url}/api/onchain/agents",
        params={"search": search_term, "protocol": protocol, "x402": True, "verified": True, "sort": "rank"},
        timeout=40,
    )
    assert response.status_code == 200
    filtered = response.json()["items"]
    for item in filtered:
        assert item["chain_id"] == 56
        assert protocol in item.get("supported_protocols", [])
        assert item["x402_supported"] is True
        assert item["is_verified"] is True


def test_onchain_sort_feedback_desc(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents", params={"sort": "feedback"}, timeout=40)
    assert response.status_code == 200
    items = response.json()["items"]
    feedbacks = [item["total_feedbacks"] for item in items]
    assert feedbacks == sorted(feedbacks, reverse=True)


# Token detail endpoint tests
def test_onchain_agent_detail_valid(api_client: requests.Session, api_base_url: str):
    list_response = api_client.get(f"{api_base_url}/api/onchain/agents", timeout=40)
    token_id = list_response.json()["items"][0]["token_id"]
    response = api_client.get(f"{api_base_url}/api/onchain/agents/{token_id}", timeout=30)
    assert response.status_code == 200
    item = response.json()
    assert item["token_id"] == token_id
    assert item["chain_id"] == 56
    assert item["source"] == "8004scan"
    assert "raw_8004scan" not in item


def test_onchain_agent_detail_404_for_missing(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents/999999999", timeout=30)
    assert response.status_code == 404


# Mongo uniqueness and sync persistence tests
def test_mongo_scan_agents_unique_and_not_duplicated(mongo_db):
    docs = list(mongo_db.scan_agents.find({"chain_id": 56}, {"_id": 0, "chain_id": 1, "token_id": 1}))
    assert len(docs) == 100
    pairs = {(row["chain_id"], row["token_id"]) for row in docs}
    assert len(pairs) == len(docs)

    indexes = list(mongo_db.scan_agents.list_indexes())
    compound_unique = [idx for idx in indexes if idx.get("key") == {"chain_id": 1, "token_id": 1} and idx.get("unique")]
    assert len(compound_unique) == 1


def test_mongo_raw_payload_stored_separately_and_projection_public(mongo_db):
    one = mongo_db.scan_agents.find_one({"chain_id": 56}, {"_id": 0})
    assert one is not None
    assert "raw_8004scan" in one
    assert isinstance(one["raw_8004scan"], dict)


def test_frontend_bundle_does_not_expose_scan_key(api_client: requests.Session, api_base_url: str):
    html = api_client.get(api_base_url, timeout=30)
    assert html.status_code == 200
    body = html.text
    assert "SCAN8004_API_KEY" not in body
    assert "X-API-Key" not in body

    script_paths = []
    for chunk in body.split("src="):
        if "/assets/" in chunk and ".js" in chunk:
            script_paths.append(chunk.split('"')[1])

    for script_path in script_paths[:12]:
        script_response = api_client.get(f"{api_base_url}{script_path}", timeout=30)
        assert script_response.status_code == 200
        script_text = script_response.text
        assert "SCAN8004_API_KEY" not in script_text
        assert "X-API-Key" not in script_text


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def update_one(self, _query, _update, upsert=False):
        return {"ok": 1, "upsert": upsert}


class _FakeDb:
    def __init__(self):
        self.scan_agents = _FakeCollection(docs=[{"chain_id": 56, "token_id": 1}, {"chain_id": 56, "token_id": 2}])
        self.scan_feedbacks = _FakeCollection(docs=[{"chain_id": 56, "feedback_id": "f1"}, {"chain_id": 56, "feedback_id": "f2"}])
        self.sync_runs = _FakeCollection()


@pytest.mark.anyio
async def test_provider_failure_keeps_last_known_good_data(monkeypatch):
    async def _raise_failure(_self, page=1, limit=100):
        raise Scan8004Error("forced provider outage")

    monkeypatch.setattr(Scan8004Client, "list_bsc_mainnet", _raise_failure)

    fake_db = _FakeDb()
    before = list(fake_db.scan_agents.docs)
    result = await sync_bsc_mainnet(fake_db)
    after = list(fake_db.scan_agents.docs)

    assert result["status"] == "degraded"
    assert result["source"] == "8004scan"
    assert result["chain_id"] == 56
    assert result["is_testnet"] is False
    assert before == after


@pytest.mark.anyio
async def test_feedback_provider_failure_keeps_last_known_good_data(monkeypatch):
    async def _raise_feedback_failure(_self, chain_id, is_testnet, page=1, limit=100):
        raise Scan8004Error("forced feedback provider outage")

    monkeypatch.setattr(Scan8004Client, "list_feedbacks", _raise_feedback_failure)

    fake_db = _FakeDb()
    before = list(fake_db.scan_feedbacks.docs)
    result = await sync_feedbacks(fake_db, 56, False)
    after = list(fake_db.scan_feedbacks.docs)

    assert result["status"] == "degraded"
    assert result["source"] == "8004scan_feedbacks"
    assert result["chain_id"] == 56
    assert result["is_testnet"] is False
    assert before == after
