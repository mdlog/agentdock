import asyncio
from datetime import datetime, timezone
import os
import random
from typing import Any

import httpx


SOURCE = "8004scan"
MAINNET_CHAIN_ID = 56
TESTNET_CHAIN_ID = 97


class Scan8004Error(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scan8004Client:
    def __init__(self):
        self.base_url = os.environ["SCAN8004_BASE_URL"].rstrip("/")
        self.api_key = os.environ["SCAN8004_API_KEY"]
        self.timeout = httpx.Timeout(45, connect=8)

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as http:
                    response = await http.get(
                        f"{self.base_url}{path}",
                        params=params,
                        headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                    )
                if response.status_code == 429:
                    if attempt == 2:
                        raise Scan8004Error("8004scan rate limit exhausted")
                    retry_after = response.headers.get("Retry-After")
                    delay = min(float(retry_after), 60) if retry_after else min(2 ** attempt, 8) + random.random()
                    await asyncio.sleep(delay)
                    continue
                if response.status_code in (408, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(min(2 ** attempt, 8) + random.random())
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise Scan8004Error("8004scan unavailable") from exc
                await asyncio.sleep(min(2 ** attempt, 8) + random.random())
        raise Scan8004Error("8004scan request failed")

    async def _list_agents(self, chain_id: int, is_testnet: bool, page: int, limit: int) -> tuple[list[dict], dict, dict]:
        response = await self._get("/agents", {
            "page": page,
            "limit": limit,
            "chainId": chain_id,
            "isTestnet": str(is_testnet).lower(),
            "sortBy": "total_score",
            "sortOrder": "desc",
        })
        try:
            payload = response.json()
            data = payload["data"]
            pagination = payload["meta"]["pagination"]
        except (ValueError, KeyError, TypeError) as exc:
            raise Scan8004Error("Malformed 8004scan response") from exc
        if not isinstance(data, list) or pagination.get("page") != page:
            raise Scan8004Error("Invalid 8004scan pagination response")
        if any(row.get("chain_id") != chain_id or row.get("is_testnet") is not is_testnet for row in data):
            raise Scan8004Error("8004scan returned records outside the requested BSC network")
        rate = {
            "limit": response.headers.get("X-RateLimit-Limit"),
            "remaining": response.headers.get("X-RateLimit-Remaining"),
            "reset": response.headers.get("X-RateLimit-Reset"),
        }
        return data, pagination, rate

    async def list_bsc_mainnet(self, page: int = 1, limit: int = 100) -> tuple[list[dict], dict, dict]:
        return await self._list_agents(MAINNET_CHAIN_ID, False, page, limit)

    async def list_bsc_testnet(self, page: int = 1, limit: int = 100) -> tuple[list[dict], dict, dict]:
        return await self._list_agents(TESTNET_CHAIN_ID, True, page, limit)

    async def list_feedbacks(self, chain_id: int, is_testnet: bool, page: int = 1, limit: int = 100) -> tuple[list[dict], dict]:
        response = await self._get("/feedbacks", {"page": page, "limit": limit, "chainId": chain_id})
        try:
            payload = response.json()
            data = payload["data"]
            pagination = payload["meta"]["pagination"]
        except (ValueError, KeyError, TypeError) as exc:
            raise Scan8004Error("Malformed 8004scan feedback response") from exc
        valid = [row for row in data if row.get("chain_id") == chain_id and row.get("is_testnet") is is_testnet]
        return valid, pagination


def public_projection(raw: dict, chain_id: int, is_testnet: bool) -> dict:
    token_id = int(raw["token_id"])
    return {
        "id": f"bsc-{chain_id}-{token_id}",
        "chain_id": chain_id,
        "is_testnet": is_testnet,
        "token_id": token_id,
        "name": raw.get("name") or f"ERC-8004 Agent #{token_id}",
        "description": raw.get("description") or "No public description supplied.",
        # Keep remote image claims only in raw_8004scan. Public cards use local
        # initials so untrusted localhost/http/CORS origins are never loaded.
        "image_url": None,
        "has_source_icon": bool(raw.get("image_url")),
        "owner_address": raw.get("owner_address"),
        "contract_address": raw.get("contract_address"),
        "supported_protocols": raw.get("supported_protocols") or [],
        "x402_supported": bool(raw.get("x402_supported")),
        "is_verified": bool(raw.get("is_verified")),
        "total_score": raw.get("total_score"),
        "rank": raw.get("rank"),
        "health_score": raw.get("health_score"),
        "total_feedbacks": raw.get("total_feedbacks") or 0,
        "average_score": raw.get("average_score"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "source": SOURCE,
        "source_label": f"8004scan · BSC {'Testnet' if is_testnet else 'Mainnet'}",
    }


async def sync_bsc_mainnet(db) -> dict:
    return await _sync_agents(db, MAINNET_CHAIN_ID, False)


async def sync_bsc_testnet(db) -> dict:
    return await _sync_agents(db, TESTNET_CHAIN_ID, True)


async def _sync_agents(db, chain_id: int, is_testnet: bool) -> dict:
    started_at = utc_now()
    key = {"source": SOURCE, "chain_id": chain_id}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": started_at, "error": None}}, upsert=True)
    imported = 0
    try:
        client = Scan8004Client()
        rows, pagination, rate = await (client.list_bsc_testnet(page=1, limit=100) if is_testnet else client.list_bsc_mainnet(page=1, limit=100))
        for raw in rows:
            projection = public_projection(raw, chain_id, is_testnet)
            await db.scan_agents.update_one(
                {"chain_id": chain_id, "token_id": projection["token_id"]},
                {"$set": {**projection, "raw_8004scan": raw, "synced_at": utc_now()}},
                upsert=True,
            )
            imported += 1
        result = {
            "status": "success",
            "source": SOURCE,
            "chain_id": chain_id,
            "is_testnet": is_testnet,
            "imported": imported,
            "available_total": pagination.get("total", imported),
            "sample_limit": 100,
            "rate_limit": rate,
            "completed_at": utc_now(),
            "error": None,
        }
        await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
        return result
    except Exception as exc:
        message = str(exc) if isinstance(exc, Scan8004Error) else "Unexpected synchronization error"
        result = {"status": "degraded", "source": SOURCE, "chain_id": chain_id, "is_testnet": is_testnet, "imported": imported, "error": message, "failed_at": utc_now()}
        await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
        return result


async def sync_feedbacks(db, chain_id: int, is_testnet: bool) -> dict:
    source = "8004scan_feedbacks"
    key = {"source": source, "chain_id": chain_id}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": utc_now()}}, upsert=True)
    try:
        rows, pagination = await Scan8004Client().list_feedbacks(chain_id, is_testnet)
        for raw in rows:
            feedback_id = str(raw.get("feedback_id") or raw.get("id"))
            await db.scan_feedbacks.update_one(
                {"chain_id": chain_id, "feedback_id": feedback_id},
                {"$set": {
                    "chain_id": chain_id,
                    "is_testnet": is_testnet,
                    "feedback_id": feedback_id,
                    "agent_id": raw.get("agent_id"),
                    "score": raw.get("score"),
                    "comment": raw.get("comment"),
                    "transaction_hash": raw.get("transaction_hash"),
                    "block_number": raw.get("block_number"),
                    "user_address": raw.get("user_address"),
                    "endpoint": raw.get("endpoint"),
                    "tags": [tag for tag in (raw.get("tag1"), raw.get("tag2")) if tag],
                    "is_revoked": bool(raw.get("is_revoked")),
                    "submitted_at": raw.get("submitted_at"),
                    "raw_8004scan": raw,
                    "synced_at": utc_now(),
                    "source": SOURCE,
                }},
                upsert=True,
            )
        result = {"status": "success", "source": source, "chain_id": chain_id, "is_testnet": is_testnet, "imported": len(rows), "available_total": pagination.get("total", len(rows)), "sample_limit": 100, "completed_at": utc_now(), "error": None}
        await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
        return result
    except Exception as exc:
        message = str(exc) if isinstance(exc, Scan8004Error) else "Unexpected feedback synchronization error"
        result = {"status": "degraded", "source": source, "chain_id": chain_id, "is_testnet": is_testnet, "imported": 0, "error": message, "failed_at": utc_now()}
        await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
        return result