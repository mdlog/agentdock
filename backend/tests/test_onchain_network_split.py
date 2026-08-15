"""Onchain network split module tests: mainnet/testnet status, agents, feedbacks, and safety."""

import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _load_backend_env() -> dict:
    return dotenv_values(Path("/app/backend/.env"))


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


def _wait_status(api_client: requests.Session, api_base_url: str, network: str) -> dict:
    payload = None
    for _ in range(30):
        response = api_client.get(
            f"{api_base_url}/api/integrations/8004scan/status",
            params={"network": network},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        if payload.get("status") == "success":
            return payload
        time.sleep(2)
    assert payload is not None
    return payload


# 8004scan per-network status module
def test_status_mainnet_success_counts(api_client: requests.Session, api_base_url: str):
    data = _wait_status(api_client, api_base_url, "mainnet")
    assert data["status"] == "success"
    assert data["chain_id"] == 56
    assert data["is_testnet"] is False
    assert data["imported"] == 100
    assert data["feedback_sample"] >= 100
    assert data["available_total"] > 100


def test_status_testnet_success_counts(api_client: requests.Session, api_base_url: str):
    data = _wait_status(api_client, api_base_url, "testnet")
    assert data["status"] == "success"
    assert data["chain_id"] == 97
    assert data["is_testnet"] is True
    assert data["imported"] == 100
    assert data["feedback_sample"] > 0
    assert data["available_total"] > 100


# Onchain agents module
def test_onchain_agents_default_remains_mainnet(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents", timeout=40)
    assert response.status_code == 200
    data = response.json()
    assert data["chain_id"] == 56
    assert data["is_testnet"] is False
    assert data["total"] == 100
    assert len(data["items"]) == 100


def test_onchain_agents_testnet_returns_100_chain97(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents", params={"network": "testnet"}, timeout=40)
    assert response.status_code == 200
    data = response.json()
    assert data["chain_id"] == 97
    assert data["is_testnet"] is True
    assert data["total"] == 100
    assert len(data["items"]) == 100
    assert all(item["chain_id"] == 97 and item["is_testnet"] is True for item in data["items"])


# Onchain feedback module
def test_feedbacks_are_isolated_per_network_and_private(api_client: requests.Session, api_base_url: str):
    mainnet = api_client.get(f"{api_base_url}/api/onchain/feedbacks", params={"network": "mainnet"}, timeout=40)
    testnet = api_client.get(f"{api_base_url}/api/onchain/feedbacks", params={"network": "testnet"}, timeout=40)

    assert mainnet.status_code == 200
    assert testnet.status_code == 200

    mainnet_items = mainnet.json()
    testnet_items = testnet.json()

    assert all(item["chain_id"] == 56 and item["is_testnet"] is False for item in mainnet_items)
    assert all(item["chain_id"] == 97 and item["is_testnet"] is True for item in testnet_items)

    for row in mainnet_items + testnet_items:
        assert "raw_8004scan" not in row
        serialized = str(row).lower()
        assert "api_key" not in serialized
        assert "x-api-key" not in serialized


# Validation module
@pytest.mark.parametrize("path", [
    "/api/integrations/8004scan/status",
    "/api/onchain/agents",
    "/api/onchain/feedbacks",
])
def test_invalid_network_rejected_400(api_client: requests.Session, api_base_url: str, path: str):
    response = api_client.get(f"{api_base_url}{path}", params={"network": "invalid"}, timeout=30)
    assert response.status_code == 400
    assert "network must be mainnet or testnet" in response.json()["detail"]


def test_onchain_agent_detail_invalid_network_rejected_400(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agents/1", params={"network": "invalid"}, timeout=30)
    assert response.status_code == 400
    assert "network must be mainnet or testnet" in response.json()["detail"]


# Mongo feedback persistence module
def test_mongo_feedback_unique_index_and_raw_private_storage(mongo_db):
    indexes = list(mongo_db.scan_feedbacks.list_indexes())
    compound_unique = [idx for idx in indexes if idx.get("key") == {"chain_id": 1, "feedback_id": 1} and idx.get("unique")]
    assert len(compound_unique) == 1

    docs = list(mongo_db.scan_feedbacks.find({}, {"_id": 0, "chain_id": 1, "feedback_id": 1, "raw_8004scan": 1}).limit(4000))
    assert len(docs) > 0
    pairs = {(row["chain_id"], row["feedback_id"]) for row in docs}
    assert len(pairs) == len(docs)
    assert any(isinstance(row.get("raw_8004scan"), dict) for row in docs)
