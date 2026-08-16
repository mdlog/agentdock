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


