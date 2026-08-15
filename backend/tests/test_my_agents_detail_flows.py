"""My Agents + full detail API tests: ownership isolation, validation, and public-field safety."""

import os
import re

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _has_forbidden_keys_or_values(value) -> bool:
    if isinstance(value, dict):
        for key, inner in value.items():
            lowered = str(key).lower()
            if "api_key" in lowered or "private_key" in lowered or "raw_8004scan" in lowered:
                return True
            if _has_forbidden_keys_or_values(inner):
                return True
        return False
    if isinstance(value, list):
        return any(_has_forbidden_keys_or_values(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "api_key" in lowered or "x-api-key" in lowered or "private key" in lowered
    return False


def _pick_owner_by_network(api_client: requests.Session, api_base_url: str, network: str) -> str:
    response = api_client.get(f"{api_base_url}/api/onchain/agents", params={"network": network}, timeout=40)
    assert response.status_code == 200
    items = response.json()["items"]
    for item in items:
        owner = item.get("owner_address")
        if isinstance(owner, str) and re.fullmatch(r"0x[a-fA-F0-9]{40}", owner):
            return owner
    pytest.skip(f"No owner address found in synchronized {network} sample")


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


# My Agents endpoint module tests
def test_my_agents_invalid_wallet_rejected_400(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/my-agents/not-a-wallet", timeout=30)
    assert response.status_code == 400
    assert "valid evm wallet address" in response.json()["detail"].lower()


def test_my_agents_invalid_network_rejected_400(api_client: requests.Session, api_base_url: str):
    response = api_client.get(
        f"{api_base_url}/api/my-agents/0x1111111111111111111111111111111111111111",
        params={"network": "invalid"},
        timeout=30,
    )
    assert response.status_code == 400
    assert "network must be mainnet or testnet" in response.json()["detail"]


@pytest.mark.parametrize(
    "network,expected_chain_id,expected_is_testnet",
    [("mainnet", 56, False), ("testnet", 97, True)],
)
def test_my_agents_owner_isolated_per_network_and_public_only(
    api_client: requests.Session,
    api_base_url: str,
    network: str,
    expected_chain_id: int,
    expected_is_testnet: bool,
):
    owner = _pick_owner_by_network(api_client, api_base_url, network)
    response = api_client.get(
        f"{api_base_url}/api/my-agents/{owner}",
        params={"network": network},
        timeout=45,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["owner_address"].lower() == owner.lower()
    assert data["network"] == network
    assert data["source"] in ["8004scan", "last_known_good"]
    assert isinstance(data["items"], list)
    assert _has_forbidden_keys_or_values(data) is False

    for item in data["items"]:
        assert item["chain_id"] == expected_chain_id
        assert item["is_testnet"] is expected_is_testnet
        assert item["owner_address"].lower() == owner.lower()
        assert "raw_8004scan" not in item


# Full detail endpoint module tests
@pytest.mark.parametrize("network", ["mainnet", "testnet"])
def test_onchain_agent_detail_returns_public_fields(api_client: requests.Session, api_base_url: str, network: str):
    list_response = api_client.get(f"{api_base_url}/api/onchain/agents", params={"network": network}, timeout=40)
    assert list_response.status_code == 200
    first = list_response.json()["items"][0]
    token_id = first["token_id"]

    response = api_client.get(f"{api_base_url}/api/onchain/agent-details/{network}/{token_id}", timeout=60)
    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] in ["8004scan_live", "last_known_good"]
    assert "fetched_at" in payload
    assert isinstance(payload["feedbacks"], list)
    assert isinstance(payload["agent"], dict)

    agent = payload["agent"]
    expected_keys = [
        "owner_address",
        "creator_address",
        "contract_address",
        "services",
        "x402_supported",
        "total_score",
        "rank",
        "health_score",
        "health_status",
        "total_validations",
        "successful_validations",
        "created_tx_hash",
        "created_block_number",
    ]
    for key in expected_keys:
        assert key in agent

    assert _has_forbidden_keys_or_values(payload) is False


def test_onchain_agent_detail_invalid_network_rejected_400(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agent-details/invalid/1", timeout=30)
    assert response.status_code == 400
    assert "network must be mainnet or testnet" in response.json()["detail"]


def test_onchain_agent_detail_missing_returns_404(api_client: requests.Session, api_base_url: str):
    response = api_client.get(f"{api_base_url}/api/onchain/agent-details/mainnet/999999999", timeout=45)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

