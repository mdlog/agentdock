"""API regression tests for AgentDock MVP research-only marketplace."""

import os
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


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


# System and readiness module tests
def test_health_ok(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/health", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_readiness_flags_expected_when_integrations_unconfigured(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/integrations/readiness", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["chain_id"] == 56
    assert data["rpc_reachable"] is True
    assert data["registry_has_code"] is True
    assert data["b402_ready"] is False
    assert data["agent_endpoints_ready"] is False
    assert data["object_storage_ready"] is False
    assert data["storage_mode"] == "mongodb_fallback"


# Agent catalog and comparison module tests
def test_agents_catalog_total_and_categories(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/agents", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 20
    assert len(data["items"]) == 20
    assert len(data["categories"]) == 4


def test_agents_active_default_count(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 18
    assert all(item["status"] == "active" for item in data["items"])


def test_agents_search_filter_sort_work(api_client: requests.Session, api_base_url: str):
    response = api_client.get(
        f"{api_base_url}/api/agents",
        params={"search": "yield", "category": "Yield Research", "status": "active", "sort": "price_low"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    prices = [item["price_usd"] for item in data["items"]]
    assert prices == sorted(prices)


def test_compare_accepts_two_to_three_distinct_ids(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"]
    two_ids = [active[0]["id"], active[1]["id"]]
    response_two = api_client.post(f"{api_base_url}/api/agents/compare", json={"agent_ids": two_ids}, timeout=20)
    assert response_two.status_code == 200
    data_two = response_two.json()
    assert [item["id"] for item in data_two] == two_ids

    three_ids = [active[0]["id"], active[1]["id"], active[2]["id"]]
    response_three = api_client.post(f"{api_base_url}/api/agents/compare", json={"agent_ids": three_ids}, timeout=20)
    assert response_three.status_code == 200
    data_three = response_three.json()
    assert [item["id"] for item in data_three] == three_ids


def test_compare_rejects_duplicate_ids(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"]
    dup_id = active[0]["id"]
    response = api_client.post(f"{api_base_url}/api/agents/compare", json={"agent_ids": [dup_id, dup_id]}, timeout=20)
    assert response.status_code == 400
    assert "distinct" in response.json()["detail"].lower()


# Task creation and safety module tests
def test_offline_agent_cannot_be_hired(api_client: requests.Session, api_base_url: str):
    offline = api_client.get(f"{api_base_url}/api/agents", params={"status": "offline"}, timeout=20).json()["items"][0]
    payload = {
        "agent_id": offline["id"],
        "objective": "TEST_ Offline hire must be blocked by server policy.",
        "constraints": "Research-only request without execution.",
    }
    response = api_client.post(f"{api_base_url}/api/tasks", json=payload, timeout=20)
    assert response.status_code == 409
    assert "offline" in response.json()["detail"].lower()


def test_unsafe_task_request_rejected_422(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"][0]
    payload = {
        "agent_id": active["id"],
        "objective": "TEST_ Please execute swap from BNB to USDT for me now.",
        "constraints": "Proceed instantly.",
    }
    response = api_client.post(f"{api_base_url}/api/tasks", json=payload, timeout=20)
    assert response.status_code == 422
    assert "unsafe request rejected" in response.json()["detail"].lower()


def test_task_create_and_get_has_single_created_audit_event(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"][0]
    payload = {
        "agent_id": active["id"],
        "objective": f"TEST_ Build neutral research brief {uuid.uuid4()} for stable BSC yields.",
        "constraints": "No swaps, no approvals, evidence from recent data.",
    }
    create_response = api_client.post(f"{api_base_url}/api/tasks", json=payload, timeout=20)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["state"] == "created"
    assert created["agent_id"] == active["id"]

    task_id = created["id"]
    get_response = api_client.get(f"{api_base_url}/api/tasks/{task_id}", timeout=20)
    assert get_response.status_code == 200
    detail = get_response.json()
    assert detail["task"]["id"] == task_id
    task_created_events = [event for event in detail["audit_events"] if event["event"] == "task.created"]
    assert len(task_created_events) == 1


def test_quote_rejects_invalid_wallet_422(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"][0]
    task_payload = {
        "agent_id": active["id"],
        "objective": f"TEST_ quote invalid wallet flow {uuid.uuid4()}.",
        "constraints": "Research only, no tx.",
    }
    task = api_client.post(f"{api_base_url}/api/tasks", json=task_payload, timeout=20).json()

    response = api_client.post(
        f"{api_base_url}/api/tasks/{task['id']}/quote",
        json={"payer": "invalid-wallet"},
        timeout=20,
    )
    assert response.status_code == 422
    assert "valid evm payer address" in response.json()["detail"].lower()


def test_quote_returns_503_when_b402_not_configured(api_client: requests.Session, api_base_url: str):
    active = api_client.get(f"{api_base_url}/api/agents", params={"status": "active"}, timeout=20).json()["items"][0]
    task_payload = {
        "agent_id": active["id"],
        "objective": f"TEST_ quote disabled flow {uuid.uuid4()} for payment lock validation.",
        "constraints": "Research only with no execution.",
    }
    task = api_client.post(f"{api_base_url}/api/tasks", json=task_payload, timeout=20).json()

    response = api_client.post(
        f"{api_base_url}/api/tasks/{task['id']}/quote",
        json={"payer": "0x1111111111111111111111111111111111111111"},
        timeout=20,
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


# PancakeSwap reference endpoint test
def test_pancakeswap_is_read_only_reference_snapshot(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/pancakeswap/pools", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["read_only"] is True
    assert data["mode"] == "reference_snapshot"
    assert len(data["items"]) >= 1
