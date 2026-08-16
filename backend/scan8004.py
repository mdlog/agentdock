import asyncio
from datetime import datetime, timezone
import os
import random
import re
from typing import Any

import httpx


SOURCE = "8004scan"

# The four agent categories the BNB Agent Studio marketplace is judged on. Each
# is derived from an agent's own on-chain name/description — real registered
# agents that say they do this work — never invented. The patterns are kept
# reasonably tight; grid especially, since the bare word "grid" over-matches.
AGENT_CATEGORIES = [
    {"key": "rebalancing", "label": "Rebalancing", "blurb": "Manages LP ranges and resets positions automatically.",
     "pattern": r"rebalanc|reset(ting)? position|lp range|concentrated liquidity|\bclmm\b|position manager|range order"},
    {"key": "grid-trading", "label": "Grid Trading", "blurb": "Places and manages automated grid orders.",
     # \bgrid\b (not a substring) so "hybrid" et al. do not match, but a
     # "Grid-*.agent" or a bot that mentions grid/DCA does — these are real
     # grid-trading agents in a DeFi registry.
     "pattern": r"\bgrid\b|\bdca\b|dollar[ -]?cost|automated (order|trading)"},
    {"key": "yield-optimisation", "label": "Yield Optimisation", "blurb": "Routes liquidity to the highest available APR.",
     "pattern": r"yield|\bapr\b|\bapy\b|farming|optimi[sz]|auto[ -]?compound|vault|staking reward|liquidity mining"},
    {"key": "health-factor", "label": "Health Factor Monitoring", "blurb": "Protects lending positions from liquidation.",
     "pattern": r"health factor|liquidation|collateral|\bltv\b|lending position|loan[ -]?to[ -]?value|borrow position|margin call"},
]
_CATEGORY_RES = [(c["key"], re.compile(c["pattern"], re.IGNORECASE)) for c in AGENT_CATEGORIES]


# What an agent's own tool vocabulary says about the job it does. Applied to
# tool names and their descriptions, which are far more precise than a
# marketing blurb: "CMC.agent" was filed under grid trading because its
# description mentions an "interactive features grid" on a landing page, while
# an agent whose tools are getSupplyAPR and getBorrowAPR is unmistakably about
# lending regardless of what it calls itself.
_CAPABILITY_PATTERNS = [
    # Deliberately excludes a bare "position": in a DEX it means an LP range, in
    # a lending protocol it means a loan, and matching it filed Aave and the
    # Lending Guardian as rebalancing agents.
    ("rebalancing", r"rebalanc|\bticks?\b|price range|concentrated|\bclmm\b|lp ?range|"
                    r"increase liquidity|decrease liquidity|collect ?fees|mint ?position"),
    ("grid-trading", r"\bgrid\b|\bdca\b|dollar[ -]?cost|limit ?order|ladder|\btwap\b"),
    ("yield-optimisation", r"\bapr\b|\bapy\b|yield|vault|farm|harvest|compound|emission|"
                           r"\bgauge\b|staking reward|\bbribe\b|best rate"),
    ("health-factor", r"health ?factor|liquidat|collateral|\bltv\b|loan[ -]?to[ -]?value|"
                      r"borrow|\bdebt\b|repay|margin|risk band|stress ?test"),
]
_CAPABILITY_RES = [(key, re.compile(pattern, re.IGNORECASE)) for key, pattern in _CAPABILITY_PATTERNS]


def derive_categories_from_capabilities(capabilities: list[dict]) -> list[str]:
    """Classify an agent by the tools it declares, not by what it calls itself.

    Only meaningful for agents whose endpoint answered, which is the point: a
    verdict drawn from a live tool list is evidence, where one drawn from a name
    is a guess. Returns [] when the tools say nothing recognisable, so an agent
    is never filed under a category to make a number look better.
    """
    corpus = " ".join(
        f"{cap.get('name', '')} {cap.get('description', '')}" for cap in capabilities or []
    )
    if not corpus.strip():
        return []
    return [key for key, expression in _CAPABILITY_RES if expression.search(corpus)]


def derive_categories(name: str | None, description: str | None) -> list[str]:
    text = f"{name or ''} {description or ''}"
    return [key for key, rx in _CATEGORY_RES if rx.search(text)]


MAINNET_CHAIN_ID = 56
TESTNET_CHAIN_ID = 97

# Identify the client honestly. Without a User-Agent, httpx sends its own default
# and Cloudflare eventually answers 403 (code 1010) on signature alone — it let
# 47,600 rows through before escalating mid-run. A descriptive agent string is
# accepted; nothing here pretends to be a browser.
USER_AGENT = "AgentDock/1.0 (+https://github.com/mdlog/agentdock)"


# What the live agents actually cover, in words a visitor would use. The
# marketplace headline rotates through these, so it must never name something
# the catalogue cannot answer: each theme is counted from the tool lists and
# descriptions of agents whose endpoints answered, and a theme with no agents
# behind it simply does not appear.
MARKETPLACE_THEMES = [
    ("market data", r"price|market|stats|screener|token info|chart"),
    ("liquidity", r"liquidity|\bpool\b|\blp\b|tick|concentrated"),
    ("swaps", r"\bswap\b|quote|route|\bdex\b|trade"),
    ("yield", r"\bapr\b|\bapy\b|yield|vault|farm|harvest|compound|stake|gauge"),
    ("payments", r"payment|invoice|x402|transfer"),
    ("lending", r"borrow|repay|collateral|health ?factor|liquidat|\bltv\b|lend"),
    ("marketing", r"marketing|campaign|ranking|content"),
    ("bridging", r"bridge|cross[- ]?chain"),
    ("governance", r"\bvote\b|governance|bribe|proposal"),
    ("predictions", r"predict|odds|forecast|signal"),
]
_THEME_RES = [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in MARKETPLACE_THEMES]


def derive_themes(agents: list[dict]) -> list[dict]:
    """Count how many live agents cover each theme, most-covered first."""
    counts: dict[str, int] = {}
    for agent in agents:
        corpus = " ".join(
            [agent.get("name") or "", agent.get("description") or ""]
            + [f"{c.get('name', '')} {c.get('description', '')}" for c in (agent.get("capabilities") or [])]
        )
        for label, expression in _THEME_RES:
            if expression.search(corpus):
                counts[label] = counts.get(label, 0) + 1
    return [{"label": label, "agents": n} for label, n in sorted(counts.items(), key=lambda kv: -kv[1])]


def effective_categories(name: str, description: str, capabilities: list[dict] | None) -> tuple[list[str], str]:
    """Categories for an agent, plus what they were derived from.

    A live tool list is evidence and outranks a name: "Fly Marketing Agent" was
    filed under yield optimisation because its blurb says "optimise", and its
    three tools are about shop marketing. An empty tool list means we could not
    read one — an A2A agent publishes no tools/list — so the metadata verdict
    stands rather than being erased by a silence we caused.
    """
    if capabilities:
        return derive_categories_from_capabilities(capabilities), "capabilities"
    return derive_categories(name, description), "metadata"


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

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            # 8004scan's docs and OpenAPI spec both say X-API-Key, but as of
            # 2026-08-15 the deployed API ignores that header everywhere and
            # honors the key only as an Authorization bearer token on /api/v1/*
            # (measured: bearer lifts limits from 180/min to 3000/min, a bogus
            # bearer falls back to anonymous, X-API-Key never changes anything).
            # Send both: the working transport now, the documented one for the
            # day they fix it.
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get(self, path: str, params: dict[str, Any], base: str | None = None) -> httpx.Response:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as http:
                    response = await http.get(
                        f"{base or self.base_url}{path}",
                        params=params,
                        headers=self._headers(),
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
                # raise_for_status raises httpx.HTTPStatusError, which callers do
                # not catch — a missing token (upstream 404) then escaped as a
                # bare 500 from the route. Convert every error status here so it
                # surfaces as a Scan8004Error the routes already handle (falling
                # back to cache, then 404).
                if response.status_code >= 400:
                    raise Scan8004Error(f"8004scan returned HTTP {response.status_code}")
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

    async def list_all_agents(self, chain_id: int, offset: int, limit: int = 100, extra_params: dict | None = None) -> tuple[list[dict], int | None]:
        """Offset-paged listing from the 180/min route, for full-catalog ingestion.

        Note the parameter name: this route filters on `chain_id`, while /public
        wants `chainId`. Passing the camelCase spelling here is silently ignored
        and returns agents from every chain mixed together.
        """
        response = await self._get("/agents", {"chain_id": chain_id, "limit": limit, "offset": offset, **(extra_params or {})}, base=self.detail_base_url)
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

    async def list_feedbacks(self, chain_id: int, is_testnet: bool, offset: int = 0, limit: int = 100) -> tuple[list[dict], int | None]:
        """Offset-paged feedback from the 180/min route.

        Three things about this endpoint had to be measured rather than assumed,
        and each mirrors the agents route: the fast base filters on `chain_id`
        while /public wants `chainId` (passing chain_id there returns all
        3.5 million rows across every chain); the response is {items, total},
        not {data, meta.pagination}; and `page` is ignored — page 2 returns page
        1 byte for byte, so paging has to use `offset`.
        """
        response = await self._get("/feedbacks", {"offset": offset, "limit": limit, "chain_id": chain_id},
                                   base=self.detail_base_url)
        try:
            payload = response.json()
            items = payload["items"]
        except (ValueError, KeyError, TypeError) as exc:
            raise Scan8004Error("Malformed 8004scan feedback response") from exc
        if not isinstance(items, list):
            raise Scan8004Error("Malformed 8004scan feedback response")
        valid = [row for row in items if row.get("chain_id") == chain_id and row.get("is_testnet") is is_testnet]
        return valid, payload.get("total")

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
    name = raw.get("name") or f"ERC-8004 Agent #{token_id}"
    description = raw.get("description") or "No public description supplied."
    return {
        "id": f"bsc-{chain_id}-{token_id}",
        "chain_id": chain_id,
        "is_testnet": is_testnet,
        "token_id": token_id,
        "name": name,
        "description": description,
        # Derived from the agent's own metadata so new syncs are tagged without a
        # backfill. Real agents, real self-description — see derive_categories.
        "categories": derive_categories(name, description),
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


async def sync_all_agents(db, chain_id: int = MAINNET_CHAIN_ID, page_size: int = 100, pace: float = 0.4, concurrency: int = 6, start_offset: int = 0, extra_params: dict | None = None, stop_when_complete: bool = False) -> dict:
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
    # Deep-offset pages are compute-bound on their side: ~30-45s each past
    # offset ~100k. The default 45s budget turned that into spurious failures;
    # the authenticated tier makes patience cheap.
    client.timeout = httpx.Timeout(120, connect=10)
    imported, offset, available = 0, start_offset, None
    try:
        while True:
            offsets = [offset + i * page_size for i in range(concurrency)]
            # Retry the batch rather than abandoning the run. Over tens of
            # minutes the upstream will drop a request or two; a single failure
            # used to end the whole sync and forfeit the remaining catalogue.
            for attempt in range(4):
                try:
                    pages = await asyncio.gather(*(client.list_all_agents(chain_id, o, page_size, extra_params) for o in offsets))
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
            # A gap-filling crawl overlaps rows the catalogue already holds. The
            # moment the stored count reaches the upstream total, everything
            # after this point is duplicate work at the most expensive offsets —
            # so a completeness-directed run declares itself done instead.
            if stop_when_complete and available is not None:
                stored = await db.scan_agents.count_documents({"chain_id": chain_id})
                if stored >= available:
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


HEAD_SYNC_SOURCE = "8004scan_head"


async def sync_new_agents(db, chain_id: int = MAINNET_CHAIN_ID, page_size: int = 100, max_pages: int = 30) -> dict:
    """Catch registrations made since the last pass.

    The registry grows continuously, so any one-shot crawl ends slightly behind.
    New agents carry the highest token ids, which the default (newest-first)
    ordering serves from offset 0 — the one place this API is fast. Walking
    newest-first until a whole page is already known therefore stays a
    seconds-long operation forever, no matter how large the catalogue gets.

    One page of overlap is tolerated before stopping: concurrent registrations
    can reorder the head between requests, and stopping on the first known row
    would miss rows pushed one page deeper.
    """
    key = {"source": HEAD_SYNC_SOURCE, "chain_id": chain_id}
    client = Scan8004Client()
    imported = scanned = 0
    available = None
    try:
        from pymongo import UpdateOne

        for page_index in range(max_pages):
            rows, total = await client.list_all_agents(chain_id, page_index * page_size, page_size)
            if total is not None:
                available = total
            if not rows:
                break
            token_ids = [int(r["token_id"]) for r in rows if r.get("token_id") is not None]
            known = await db.scan_agents.count_documents({"chain_id": chain_id, "token_id": {"$in": token_ids}})
            ops = []
            for raw in rows:
                projection = public_projection(raw, chain_id, bool(raw.get("is_testnet")))
                ops.append(UpdateOne(
                    {"chain_id": chain_id, "token_id": projection["token_id"]},
                    {"$set": {**projection, "raw_8004scan": raw, "synced_at": utc_now()}},
                    upsert=True,
                ))
            outcome = await db.scan_agents.bulk_write(ops, ordered=False)
            imported += outcome.upserted_count
            scanned += len(rows)
            if known == len(rows):
                break
            await asyncio.sleep(0.4)
        result = {"status": "success", "source": HEAD_SYNC_SOURCE, "chain_id": chain_id,
                  "new_agents": imported, "scanned": scanned, "available_total": available,
                  "completed_at": utc_now(), "error": None}
    except Exception as exc:
        message = str(exc) if isinstance(exc, Scan8004Error) else "Unexpected head synchronization error"
        result = {"status": "degraded", "source": HEAD_SYNC_SOURCE, "chain_id": chain_id,
                  "new_agents": imported, "error": message, "failed_at": utc_now()}
    await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
    return result


async def sync_feedbacks(db, chain_id: int, is_testnet: bool, max_pages: int = 200) -> dict:
    source = "8004scan_feedbacks"
    key = {"source": source, "chain_id": chain_id}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": utc_now()}}, upsert=True)
    try:
        # One page was being synced — 100 entries against 11,680 the catalogue
        # reports — so almost every agent's detail page showed none. Walk the
        # pages until the source runs out.
        client = Scan8004Client()
        rows: list[dict] = []
        offset, available = 0, None
        while offset < max_pages * 100:
            batch, total = await client.list_feedbacks(chain_id, is_testnet, offset=offset)
            if total is not None:
                available = total
            if not batch:
                break
            rows.extend(batch)
            offset += 100
            if available is not None and offset >= available:
                break
            await asyncio.sleep(0.35)
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