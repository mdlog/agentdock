import asyncio
from datetime import datetime, timezone
import os
import random
from typing import Any

import httpx


SOURCE = "8004scan"
MAINNET_CHAIN_ID = 56
TESTNET_CHAIN_ID = 97

# Identify the client honestly. Without a User-Agent, httpx sends its own default
# and Cloudflare eventually answers 403 (code 1010) on signature alone — it let
# 47,600 rows through before escalating mid-run. A descriptive agent string is
# accepted; nothing here pretends to be a browser.
USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"


class Scan8004Error(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scan8004Client:
    def __init__(self):
        self.base_url = os.environ["SCAN8004_BASE_URL"].rstrip("/")
        # Detail lookups go to the non-/public route. Both are unauthenticated —
        # the key is ignored on either — but /public allows 10 requests a minute
        # while this one allows 180, which is the difference between resolving
        # every synced agent's endpoint in under a minute and taking ten. It
        # returns the agent object unwrapped, where /public wraps it in `data`.
        self.detail_base_url = os.environ.get("SCAN8004_DETAIL_BASE_URL") or self.base_url.removesuffix("/public").rstrip("/")
        self.api_key = os.environ["SCAN8004_API_KEY"]
        self.timeout = httpx.Timeout(45, connect=8)

    async def _get(self, path: str, params: dict[str, Any], base: str | None = None) -> httpx.Response:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as http:
                    response = await http.get(
                        f"{base or self.base_url}{path}",
                        params=params,
                        headers={"X-API-Key": self.api_key, "Accept": "application/json", "User-Agent": USER_AGENT},
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

    async def list_all_agents(self, chain_id: int, offset: int, limit: int = 100) -> tuple[list[dict], int | None]:
        """Offset-paged listing from the 180/min route, for full-catalog ingestion.

        Note the parameter name: this route filters on `chain_id`, while /public
        wants `chainId`. Passing the camelCase spelling here is silently ignored
        and returns agents from every chain mixed together.
        """
        response = await self._get("/agents", {"chain_id": chain_id, "limit": limit, "offset": offset}, base=self.detail_base_url)
        try:
            payload = response.json()
            items = payload.get("items")
        except (ValueError, AttributeError) as exc:
            raise Scan8004Error("Malformed 8004scan catalog response") from exc
        if not isinstance(items, list):
            raise Scan8004Error("Malformed 8004scan catalog response")
        if any(row.get("chain_id") != chain_id for row in items):
            raise Scan8004Error("8004scan returned records outside the requested chain")
        return items, payload.get("total")

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

    async def owned_agents(self, address: str, page: int = 1, limit: int = 100) -> tuple[list[dict], dict]:
        response = await self._get(f"/accounts/{address}/agents", {"page": page, "limit": limit, "sortBy": "created_at", "sortOrder": "desc"})
        try:
            payload = response.json()
            return payload["data"], payload["meta"]["pagination"]
        except (ValueError, KeyError, TypeError) as exc:
            raise Scan8004Error("Malformed 8004scan ownership response") from exc

    async def agent_detail(self, chain_id: int, token_id: int) -> dict:
        path = f"/agents/{chain_id}/{token_id}"
        try:
            response = await self._get(path, {}, base=self.detail_base_url)
            payload = response.json()
        except (Scan8004Error, ValueError):
            # The high-rate route is undocumented, so a failure there falls back
            # to /public rather than breaking agent detail outright.
            response = await self._get(path, {})
            try:
                payload = response.json()
            except ValueError as exc:
                raise Scan8004Error("Malformed 8004scan detail response") from exc
        # /public wraps the agent in `data`; the high-rate route returns it bare.
        agent = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(agent, dict) or "token_id" not in agent:
            raise Scan8004Error("Malformed 8004scan detail response")
        return agent

    async def agent_feedbacks(self, chain_id: int, token_id: int, limit: int = 20) -> list[dict]:
        response = await self._get("/feedbacks", {"page": 1, "limit": limit, "chainId": chain_id, "tokenId": token_id})
        try:
            return response.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise Scan8004Error("Malformed 8004scan feedback detail response") from exc


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


def detail_projection(raw: dict) -> dict:
    chain_id = int(raw["chain_id"])
    token_id = int(raw["token_id"])
    return {
        **public_projection(raw, chain_id, bool(raw.get("is_testnet"))),
        "agent_id": raw.get("agent_id"),
        "creator_address": raw.get("creator_address"),
        "agent_wallet": raw.get("agent_wallet"),
        "agent_type": raw.get("agent_type"),
        "tags": raw.get("tags") or [],
        "categories": raw.get("categories") or [],
        "services": raw.get("services") or {},
        "scores": raw.get("scores") or {},
        "quality_score": raw.get("quality_score"),
        "popularity_score": raw.get("popularity_score"),
        "activity_score": raw.get("activity_score"),
        "wallet_score": raw.get("wallet_score"),
        "freshness_score": raw.get("freshness_score"),
        "metadata_completeness_score": raw.get("metadata_completeness_score"),
        "supported_trust_models": raw.get("supported_trust_models") or [],
        "health_status": raw.get("health_status") or {},
        "health_checked_at": raw.get("health_checked_at"),
        "is_endpoint_verified": bool(raw.get("is_endpoint_verified")),
        "endpoint_verified_domain": raw.get("endpoint_verified_domain"),
        "endpoint_verification_error": raw.get("endpoint_verification_error"),
        "is_active": raw.get("is_active"),
        "total_validations": raw.get("total_validations") or 0,
        "successful_validations": raw.get("successful_validations") or 0,
        "created_block_number": raw.get("created_block_number"),
        "created_tx_hash": raw.get("created_tx_hash"),
        "cross_chain_links": raw.get("cross_chain_links") or [],
        "cross_chain_versions": raw.get("cross_chain_versions") or [],
        "raw_metadata": raw.get("raw_metadata") or {},
        "field_sources": raw.get("field_sources") or {},
        "parse_status": raw.get("parse_status") or {},
        "ens": raw.get("ens"),
        "did": raw.get("did"),
        "mcp_server": raw.get("mcp_server"),
        "mcp_version": raw.get("mcp_version"),
        "a2a_endpoint": raw.get("a2a_endpoint"),
        "a2a_version": raw.get("a2a_version"),
        "agent_url": raw.get("agent_url"),
    }


def feedback_projection(raw: dict) -> dict:
    return {
        "feedback_id": str(raw.get("feedback_id") or raw.get("id")),
        "score": raw.get("score"),
        "comment": raw.get("comment"),
        "transaction_hash": raw.get("transaction_hash"),
        "user_address": raw.get("user_address"),
        "tags": [tag for tag in (raw.get("tag1"), raw.get("tag2")) if tag],
        "is_revoked": bool(raw.get("is_revoked")),
        "submitted_at": raw.get("submitted_at") or raw.get("created_at"),
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


FULL_SYNC_SOURCE = "8004scan_full"


async def sync_all_agents(db, chain_id: int = MAINNET_CHAIN_ID, page_size: int = 100, pace: float = 0.4, concurrency: int = 4, start_offset: int = 0) -> dict:
    """Ingest every agent on one chain, not just the first ranked page.

    Pages are fetched `concurrency` at a time. Sequentially this managed only
    ~25 requests a minute — each round trip costs about 1.5s and nothing
    overlapped — so it used a seventh of the 180/min budget and would have taken
    over an hour. Four in flight lands near 160/min, inside the budget.

    Writes in bulk because 2500-odd single upserts would spend longer in round
    trips than in the network calls, and records `offset` after every batch so a
    failed or interrupted run can resume instead of starting over.
    """
    from pymongo import UpdateOne

    key = {"source": FULL_SYNC_SOURCE, "chain_id": chain_id}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": utc_now(), "error": None}}, upsert=True)

    client = Scan8004Client()
    imported, offset, available = 0, start_offset, None
    try:
        while True:
            offsets = [offset + i * page_size for i in range(concurrency)]
            # Retry the batch rather than abandoning the run. Over tens of
            # minutes the upstream will drop a request or two; a single failure
            # used to end the whole sync and forfeit the remaining catalogue.
            for attempt in range(4):
                try:
                    pages = await asyncio.gather(*(client.list_all_agents(chain_id, o, page_size) for o in offsets))
                    break
                except Scan8004Error:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(min(2 ** attempt, 8) + random.random())
            rows = [row for page, total in pages for row in page]
            for _, total in pages:
                if total is not None:
                    available = total
            if not rows:
                break
            ops = []
            for raw in rows:
                projection = public_projection(raw, chain_id, bool(raw.get("is_testnet")))
                ops.append(UpdateOne(
                    {"chain_id": chain_id, "token_id": projection["token_id"]},
                    {"$set": {**projection, "raw_8004scan": raw, "synced_at": utc_now()}},
                    upsert=True,
                ))
            await db.scan_agents.bulk_write(ops, ordered=False)
            imported += len(rows)
            offset += page_size * concurrency
            await db.sync_runs.update_one(key, {"$set": {"imported": imported, "available_total": available, "offset": offset}})
            if available is not None and offset >= available:
                break
            await asyncio.sleep(pace)
        result = {"status": "success", "source": FULL_SYNC_SOURCE, "chain_id": chain_id, "imported": imported, "available_total": available, "completed_at": utc_now(), "error": None}
    except Exception as exc:
        message = str(exc) if isinstance(exc, Scan8004Error) else "Unexpected full synchronization error"
        # Partial progress is kept: rows already written stay, and the run is
        # restartable from the recorded offset.
        result = {"status": "degraded", "source": FULL_SYNC_SOURCE, "chain_id": chain_id, "imported": imported, "available_total": available, "offset": offset, "error": message, "failed_at": utc_now()}
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