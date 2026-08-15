import asyncio
from datetime import datetime, timezone
import os
import random
from typing import Any

import httpx


SOURCE = "8004scan"
CHAIN_ID = 56


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

    async def list_bsc_mainnet(self, page: int = 1, limit: int = 100) -> tuple[list[dict], dict, dict]:
        response = await self._get("/agents", {
            "page": page,
            "limit": limit,
            "chainId": CHAIN_ID,
            "isTestnet": "false",
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
        if any(row.get("chain_id") != CHAIN_ID or row.get("is_testnet") is not False for row in data):
            raise Scan8004Error("8004scan returned records outside BSC Mainnet")
        rate = {
            "limit": response.headers.get("X-RateLimit-Limit"),
            "remaining": response.headers.get("X-RateLimit-Remaining"),
            "reset": response.headers.get("X-RateLimit-Reset"),
        }
        return data, pagination, rate


def public_projection(raw: dict) -> dict:
    token_id = int(raw["token_id"])
    return {
        "id": f"bsc-56-{token_id}",
        "chain_id": CHAIN_ID,
        "token_id": token_id,
        "name": raw.get("name") or f"ERC-8004 Agent #{token_id}",
        "description": raw.get("description") or "No public description supplied.",
        # Keep remote image claims only in raw_8004scan. Public cards use local
        # initials so untrusted localhost/http/CORS origins are never loaded.
        "image_url": None,
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
        "source_label": "8004scan · BSC Mainnet",
    }


async def sync_bsc_mainnet(db) -> dict:
    started_at = utc_now()
    key = {"source": SOURCE, "chain_id": CHAIN_ID}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": started_at, "error": None}}, upsert=True)
    imported = 0
    try:
        client = Scan8004Client()
        rows, pagination, rate = await client.list_bsc_mainnet(page=1, limit=100)
        for raw in rows:
            projection = public_projection(raw)
            await db.scan_agents.update_one(
                {"chain_id": CHAIN_ID, "token_id": projection["token_id"]},
                {"$set": {**projection, "raw_8004scan": raw, "synced_at": utc_now()}},
                upsert=True,
            )
            imported += 1
        result = {
            "status": "success",
            "source": SOURCE,
            "chain_id": CHAIN_ID,
            "is_testnet": False,
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
        result = {"status": "degraded", "source": SOURCE, "chain_id": CHAIN_ID, "is_testnet": False, "imported": imported, "error": message, "failed_at": utc_now()}
        await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
        return result