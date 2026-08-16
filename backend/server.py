import asyncio
from datetime import datetime, timedelta, timezone
import os
import re
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware
from urllib.parse import urlparse

import agent_client
import b402
from guards import client_key, icon_limiter, require_operator, run_limiter, task_limiter
from integrations import ArtifactStore, B402Adapter, B402Unavailable, registry_health
from models import AuditEvent, AuthorizeRequest, FeedbackRequest, IntegrationReadiness, PayRequest, QuoteRequest, ScanAgent, ScanAgentList, ScanFeedback, TaskCreate, TaskDetail, TaskRecord
from scan8004 import AGENT_CATEGORIES, Scan8004Client, Scan8004Error, detail_projection, feedback_projection, public_projection, sync_all_agents, sync_bsc_mainnet, sync_bsc_testnet, sync_feedbacks, sync_new_agents
from icon_proxy import get_agent_icon


load_dotenv()
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="AgentDock API", version="1.0.0")
api = APIRouter(prefix="/api")
# Merchant-side adapter (accepting payments). Named apart from the `b402`
# module, which is the buyer-side client used to pay other agents.
b402_merchant = B402Adapter()
artifacts = ArtifactStore()

# The settlement network AgentDock itself targets. 8004scan discovery covers both
# BSC networks independently and is not affected by this value.
CHAIN_ID = int(os.environ.get("BSC_CHAIN_ID", "56"))

# Upstream failures are reported as 4xx, not 5xx. This is not cosmetic: the
# Cloudflare edge replaces any 5xx from the origin with its own error page,
# which carries no CORS header and no body — so the browser sees a network
# failure and every honest explanation ("this agent needs its own credential",
# "check your wallet on BscScan before retrying") is erased before the user
# reads it. 424 is also the truthful code: the request was fine, something we
# depend on was not.
UPSTREAM_FAILED = 424       # Failed Dependency
UPSTREAM_UNAVAILABLE = 409  # Conflict: a dependency is not configured


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def audit(task_id: str, event: str, detail: str) -> None:
    await db.audit_events.insert_one({"id": str(uuid.uuid4()), "task_id": task_id, "event": event, "detail": detail, "created_at": now_iso()})


@app.on_event("startup")
async def startup() -> None:
    await db.tasks.create_index("id", unique=True)
    await db.audit_events.create_index([("task_id", 1), ("created_at", 1)])
    await db.payments.create_index("tx_hash", unique=True, sparse=True)
    await db.scan_agents.create_index([("chain_id", 1), ("token_id", 1)], unique=True)
    await db.scan_agents.create_index([("name", "text"), ("description", "text")])
    # Sorting a 256k catalogue with skip/limit needs these; without them every
    # page past the first scans the collection.
    await db.scan_agents.create_index([("chain_id", 1), ("total_score", -1)])
    await db.scan_agents.create_index([("chain_id", 1), ("rank", 1)])
    await db.scan_agents.create_index([("chain_id", 1), ("total_feedbacks", -1)])
    # Category browse is the marketplace's primary journey; index it with the
    # score sort so a filtered page never scans the collection.
    await db.scan_agents.create_index([("chain_id", 1), ("categories", 1), ("total_score", -1)])
    # The default browse order. Without these the readiness sort scans the
    # whole 134k collection on every page.
    await db.scan_agents.create_index([("chain_id", 1), ("activatable", -1), ("total_score", -1)])
    await db.scan_agents.create_index([("chain_id", 1), ("categories", 1), ("activatable", -1), ("total_score", -1)])
    await db.sync_runs.create_index([("source", 1), ("chain_id", 1)], unique=True)
    await db.scan_feedbacks.create_index([("chain_id", 1), ("feedback_id", 1)], unique=True)
    await db.scan_feedbacks.create_index([("chain_id", 1), ("agent_id", 1), ("submitted_at", -1)])
    await db.scan_agent_icons.create_index([("chain_id", 1), ("token_id", 1)], unique=True)
    # A process killed mid-sync leaves its row on "running", and every later
    # trigger then 409s against a run that is not happening. Nothing can still
    # be running at startup, so those rows are reclaimed rather than believed.
    orphaned = await db.sync_runs.update_many(
        {"status": "running"},
        {"$set": {"status": "degraded", "error": "Interrupted before completion", "failed_at": now_iso()}},
    )
    if orphaned.modified_count:
        print(f"Reclaimed {orphaned.modified_count} interrupted sync run(s)")
    app.state.scan_sync_task = __import__("asyncio").create_task(sync_bsc_mainnet(db))
    app.state.scan_testnet_task = __import__("asyncio").create_task(sync_bsc_testnet(db))
    app.state.b402_sync_task = __import__("asyncio").create_task(sync_b402_catalog())
    app.state.scan_mainnet_feedback_task = __import__("asyncio").create_task(sync_feedbacks(db, 56, False))
    app.state.head_sync_task = __import__("asyncio").create_task(_head_sync_loop())
    app.state.enrich_loop_task = __import__("asyncio").create_task(_enrich_loop())
    app.state.scan_testnet_feedback_task = __import__("asyncio").create_task(sync_feedbacks(db, 97, True))


async def _head_sync_loop(interval_seconds: int = 600) -> None:
    """The registry never stops growing, so staying current is a standing job,
    not a one-shot crawl. New registrations sit at offset 0 — the only place
    the upstream API is fast — so each pass costs seconds. Restart-safe by
    construction: every pass is idempotent, and a killed loop simply resumes
    on the next boot."""
    while True:
        try:
            result = await sync_new_agents(db)
            if result.get("new_agents"):
                print(f"Head sync: +{result['new_agents']} new agents")
        except Exception as exc:  # never let the loop die on a bad pass
            print(f"Head sync pass failed: {exc}")
        await asyncio.sleep(interval_seconds)


async def _enrich_loop(interval_seconds: int = 3600) -> None:
    """Keep endpoint verdicts current for as long as the app is up.

    Runs hourly and re-probes whatever has gone stale, so the hireable pool
    tracks reality in both directions: an agent whose host dies stops offering a
    button that fails, and an operator who finally deploys their service becomes
    hireable without anyone intervening.
    """
    while True:
        try:
            key = {"source": "endpoint_enrich", "chain_id": CHAIN_ID}
            running = await db.sync_runs.find_one(key)
            if not running or running.get("status") != "running":
                result = await enrich_endpoints(CHAIN_ID)
                if result.get("checked"):
                    print(f"Endpoint re-probe: {result['checked']} checked, {result['activatable']} live")
        except Exception as exc:  # a bad pass must not end the loop
            print(f"Endpoint re-probe failed: {exc}")
        await asyncio.sleep(interval_seconds)


async def sync_b402_catalog() -> dict:
    """Discover payable BNB Chain services from Binance's public b402 Bazaar.

    Discovery only. What a task actually pays is always read from the merchant's
    live 402 challenge, because the catalog and the challenge have been observed
    to disagree on network and asset.
    """
    key = {"source": "b402_bazaar"}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": now_iso()}}, upsert=True)
    try:
        # Hard ceiling on the whole fetch. A startup task that hangs leaves the
        # status stuck on "running" forever, which reads as "still working"
        # rather than "broken" — observed once against this endpoint.
        items = await __import__("asyncio").wait_for(b402.fetch_bazaar(limit=100), timeout=60)
        projected = [p for p in (b402.bazaar_projection(item) for item in items) if p]
        for row in projected:
            await db.b402_resources.update_one({"id": row["id"]}, {"$set": {**row, "synced_at": now_iso()}}, upsert=True)
        # Recorded rather than silently dropped: a listing is skipped when it is
        # served over plain HTTP or accepts payment only off BNB Chain, and the
        # difference between listed and imported should be explainable.
        skipped = [
            {"resource": item.get("resource"), "reason": "not https" if not str(item.get("resource", "")).startswith("https://") else "no BNB Chain option"}
            for item in items if b402.bazaar_projection(item) is None
        ]
        result = {"status": "success", "source": "b402_bazaar", "imported": len(projected), "listed_total": len(items), "skipped": skipped, "completed_at": now_iso(), "error": None}
    except Exception as exc:
        result = {"status": "degraded", "source": "b402_bazaar", "imported": 0, "error": str(exc) if isinstance(exc, b402.B402Error) else "Unexpected b402 catalog error", "failed_at": now_iso()}
    await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
    return result


@api.get("/", tags=["system"])
async def root():
    return {"message": "AgentDock API", "status": "ready"}


@api.post("/b402/sync", dependencies=[Depends(require_operator)], tags=["b402"])
async def trigger_b402_sync():
    """Refresh the catalog on demand. The startup task is best-effort; this is the
    reliable path, and it surfaces the upstream error instead of hiding it."""
    return await sync_b402_catalog()


@api.get("/b402/resources", tags=["b402"])
async def list_b402_resources(search: str = ""):
    query: dict = {}
    if search:
        query["$or"] = [
            {"description": {"$regex": re.escape(search), "$options": "i"}},
            {"host": {"$regex": re.escape(search), "$options": "i"}},
        ]
    items = await db.b402_resources.find(query, {"_id": 0}).sort("host", 1).to_list(200)
    status = await db.sync_runs.find_one({"source": "b402_bazaar"}, {"_id": 0})
    return {"items": items, "total": len(items), "network": "eip155:56", "chain_id": 56, "source": "b402_bazaar", "sync": status or {"status": "never_run"}}


@api.get("/health", tags=["system"])
async def health():
    await db.command("ping")
    return {"status": "ok", "database": "connected"}


@api.get("/integrations/readiness", response_model=IntegrationReadiness, tags=["system"])
async def readiness():
    try:
        rpc_ok, code_ok = await registry_health()
    except Exception:
        rpc_ok, code_ok = False, False
    endpoints_ready = all(os.environ.get(f"AGENT_{idx}_URL") for idx in range(1, 4))
    notes = []
    if not b402_merchant.ready:
        notes.append("Binance B402 partner onboarding is required before payment can be enabled.")
    if not endpoints_ready:
        notes.append("Seed profiles are visible, but live agent endpoints are not configured.")
    if not artifacts.ready:
        notes.append("Result artifacts will use MongoDB fallback until object storage is configured.")
    return IntegrationReadiness(chain_id=CHAIN_ID, registry_configured=bool(os.environ.get("ERC8004_IDENTITY_REGISTRY")), rpc_reachable=rpc_ok, registry_has_code=code_ok, b402_ready=b402_merchant.ready, agent_endpoints_ready=endpoints_ready, object_storage_ready=artifacts.ready, storage_mode="object_storage" if artifacts.ready else "mongodb_fallback", notes=notes)


@api.post("/onchain/sync-all", dependencies=[Depends(require_operator)], tags=["agents"])
async def trigger_full_sync(network: str = "mainnet"):
    """Ingest the whole chain catalogue in the background.

    Deliberately not a startup task: it runs for about fourteen minutes, and the
    ranked first page already gives the app usable data immediately.
    """
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    previous = await db.sync_runs.find_one({"source": "8004scan_full", "chain_id": chain_id})
    if previous and previous.get("status") == "running":
        raise HTTPException(409, "A full synchronization is already running")
    # Resume where the last run stopped. Upserts are keyed on (chain_id, token_id)
    # so re-covering ground is harmless, but skipping it saves many minutes.
    start_offset = int(previous.get("offset") or 0) if previous and previous.get("status") == "degraded" else 0
    app.state.full_sync_task = __import__("asyncio").create_task(sync_all_agents(db, chain_id, start_offset=start_offset))
    return {"status": "started", "chain_id": chain_id, "start_offset": start_offset, "poll": f"/api/integrations/8004scan/status?network={network}"}


@api.get("/integrations/8004scan/status", tags=["system"])
async def scan_status(network: str = "mainnet"):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    status = await db.sync_runs.find_one({"source": "8004scan", "chain_id": chain_id}, {"_id": 0})
    full = await db.sync_runs.find_one({"source": "8004scan_full", "chain_id": chain_id}, {"_id": 0})
    feedback_count = await db.scan_feedbacks.count_documents({"chain_id": chain_id})
    stored = await db.scan_agents.count_documents({"chain_id": chain_id})
    result = status or {"status": "never_run", "source": "8004scan", "chain_id": chain_id, "is_testnet": network == "testnet"}
    return {**result, "feedback_sample": feedback_count, "stored_agents": stored, "full_sync": full or {"status": "never_run"}}


# How long a verdict is trusted before it is checked again. Endpoints come and
# go: a probe run once is a claim about the past, and over a judging window
# weeks away an unrefreshed pool can only shrink as hosts disappear — while an
# operator who deploys their service never becomes visible.
ENDPOINT_VERDICT_TTL_HOURS = 12


async def enrich_endpoints(chain_id: int = 56, limit: int = 600) -> dict:
    """Resolve callable endpoints for categorized agents and flag the activatable
    ones. Bounded to the categorized set (a few hundred) — those are what the
    marketplace browses — and paced under the 8004scan budget."""
    key = {"source": "endpoint_enrich", "chain_id": chain_id}
    await db.sync_runs.update_one(key, {"$set": {"status": "running", "started_at": now_iso()}}, upsert=True)
    # `endpoint_status` is the marker for a *probed* agent. Records from the
    # earlier metadata-only pass have none, so they are re-examined rather than
    # left carrying a claim nobody ever tested.
    stale_before = (datetime.now(timezone.utc) - timedelta(hours=ENDPOINT_VERDICT_TTL_HOURS)).isoformat()
    cursor = db.scan_agents.find(
        {"chain_id": chain_id, "categories": {"$ne": []},
         "$or": [{"endpoint_status": {"$exists": False}},
                 {"endpoint_checked_at": {"$lt": stale_before}},
                 {"endpoint_checked_at": {"$exists": False}}]},
        {"_id": 0, "id": 1, "chain_id": 1, "token_id": 1, "raw_8004scan_detail": 1},
    ).limit(limit)
    client = Scan8004Client()
    checked = activatable = 0
    try:
        # 8004scan is rate limited, so details are read in a paced pass; the
        # probes that follow hit hundreds of unrelated hosts and run concurrently.
        resolved, unknown = [], 0
        for agent in await cursor.to_list(limit):
            detail = None
            try:
                detail = await client.agent_detail(chain_id, agent["token_id"])
            except Scan8004Error:
                detail = agent.get("raw_8004scan_detail")
            if detail is None:
                # 8004scan was unreachable and nothing is cached, so we do not
                # know what this agent publishes. Recording "no endpoint" here
                # would turn our own outage into a permanent verdict about
                # somebody else's agent; leaving it unmarked lets a later pass
                # pick it up.
                unknown += 1
                await asyncio.sleep(0.34)
                continue
            resolved.append((agent, agent_client.pick_endpoint(detail)))
            await asyncio.sleep(0.34)

        gate = asyncio.Semaphore(8)
        # One host can back hundreds of registrations — 180 agents shared a single
        # card URL here. Probing them independently and concurrently made the host
        # rate-limit us, and those 429s were then recorded as facts about the
        # agents. Two caches prevent that: a URL that resolves identically for two
        # agents is probed once, and no host is asked more than one question at a
        # time. Templated URLs resolve per-agent, so they are NOT deduplicated —
        # each agent's own id may produce a different verdict.
        verdict_cache: dict[str, tuple[str, str]] = {}
        host_locks: dict[str, asyncio.Lock] = {}

        async def verify(agent: dict, ep: tuple[str, str] | None) -> tuple[dict, dict]:
            if not ep:
                return agent, {"endpoint_status": "none", "endpoint_note": "No endpoint published onchain", "activatable": False}
            kind, url = ep
            token_id = agent["token_id"]
            resolved = agent_client.substitute_agent_id(url, token_id)
            cache_key = f"{kind}|{resolved}"
            cached = verdict_cache.get(cache_key)
            if cached:
                status, note = cached
            else:
                host = urlparse(resolved).hostname or resolved
                async with gate:
                    async with host_locks.setdefault(host, asyncio.Lock()):
                        status, note = await agent_client.probe_endpoint(kind, url, token_id)
                        await asyncio.sleep(0.25)
                verdict_cache[cache_key] = (status, note)
            return agent, {"endpoint_kind": kind, "agent_endpoint": url, "endpoint_status": status,
                           "endpoint_note": note[:300], "activatable": status == "live"}

        for completed in asyncio.as_completed([verify(a, e) for a, e in resolved]):
            agent, update = await completed
            update["endpoint_checked"] = True
            update["endpoint_checked_at"] = now_iso()
            await db.scan_agents.update_one({"chain_id": chain_id, "token_id": agent["token_id"]}, {"$set": update})
            checked += 1
            activatable += 1 if update["activatable"] else 0
            # Progress is published as it happens: a run that only reports at the
            # end is indistinguishable from one that has hung.
            if checked % 20 == 0:
                await db.sync_runs.update_one(key, {"$set": {"checked": checked, "activatable": activatable, "total": len(resolved)}})
        result = {"status": "success", "source": "endpoint_enrich", "chain_id": chain_id, "checked": checked,
                  "activatable": activatable, "unknown": unknown, "completed_at": now_iso()}
    except Exception as exc:
        result = {"status": "degraded", "source": "endpoint_enrich", "chain_id": chain_id, "checked": checked, "activatable": activatable, "error": str(exc), "failed_at": now_iso()}
    await db.sync_runs.update_one(key, {"$set": result}, upsert=True)
    return result


@api.post("/onchain/enrich-endpoints", dependencies=[Depends(require_operator)], tags=["agents"])
async def trigger_enrich(network: str = "mainnet"):
    chain_id = 97 if network == "testnet" else 56
    running = await db.sync_runs.find_one({"source": "endpoint_enrich", "chain_id": chain_id})
    if running and running.get("status") == "running":
        raise HTTPException(409, "Endpoint enrichment already running")
    app.state.enrich_task = __import__("asyncio").create_task(enrich_endpoints(chain_id))
    return {"status": "started", "chain_id": chain_id}


@api.get("/categories", tags=["agents"])
async def list_categories(network: str = "mainnet"):
    """The four judged agent categories with live counts of real agents in each."""
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    items = []
    for cat in AGENT_CATEGORIES:
        scope = {"chain_id": chain_id, "categories": cat["key"]}
        count = await db.scan_agents.count_documents(scope)
        # A registration count sets an expectation the category may not meet. The
        # ready count is the one that predicts whether a visitor can do anything
        # here, so both are published and the card leads with the honest one.
        ready = await db.scan_agents.count_documents({**scope, "activatable": True})
        payable = await db.b402_resources.count_documents({"categories": cat["key"]})
        items.append({"key": cat["key"], "label": cat["label"], "blurb": cat["blurb"],
                      "count": count, "ready": ready, "payable": payable})
    total_tagged = await db.scan_agents.count_documents({"chain_id": chain_id, "categories": {"$ne": []}})
    return {"categories": items, "total_categorized": total_tagged, "network": network, "chain_id": chain_id}


@api.get("/onchain/agents", response_model=ScanAgentList, tags=["agents"])
async def list_onchain_agents(
    network: str = "mainnet",
    search: str = "",
    protocol: str | None = None,
    category: str | None = None,
    x402: bool | None = None,
    verified: bool | None = None,
    sort: str = "ready",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=60, ge=1, le=200),
):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id, is_testnet = (97, True) if network == "testnet" else (56, False)
    query: dict = {"chain_id": chain_id, "is_testnet": is_testnet}
    if category:
        query["categories"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": re.escape(search), "$options": "i"}},
            {"description": {"$regex": re.escape(search), "$options": "i"}},
        ]
    if protocol:
        query["supported_protocols"] = protocol
    if x402 is not None:
        query["x402_supported"] = x402
    if verified is not None:
        query["is_verified"] = verified
    sort_map = {"score": [("total_score", -1)], "rank": [("rank", 1)],
                "feedback": [("total_feedbacks", -1)], "newest": [("created_at", -1)]}
    # Default ordering puts the agents a visitor can actually use first. Nothing
    # is hidden and the totals are unchanged — a catalogue where 435 of 442
    # probed endpoints are dead simply should not lead with them.
    spec = [("activatable", -1), ("total_score", -1)] if sort == "ready" else sort_map.get(sort, sort_map["score"])
    # total is the number of matching rows, not the size of this page: the UI
    # needs it to render pagination over a catalogue it never receives whole.
    total = await db.scan_agents.count_documents(query)
    # Published alongside the total so the ordering is legible rather than
    # mysterious: the UI can say how many of these matches are actually usable.
    ready_total = await db.scan_agents.count_documents({**query, "activatable": True})
    items = await db.scan_agents.find(query, {"_id": 0, "raw_8004scan": 0}).sort(spec).skip(offset).limit(limit).to_list(limit)
    return ScanAgentList(items=items, total=total, ready_total=ready_total, chain_id=chain_id, is_testnet=is_testnet, offset=offset, limit=limit)


@api.get("/onchain/agents/{token_id}", response_model=ScanAgent, tags=["agents"])
async def get_onchain_agent(token_id: int, network: str = "mainnet"):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    item = await db.scan_agents.find_one({"chain_id": chain_id, "token_id": token_id}, {"_id": 0, "raw_8004scan": 0})
    if not item:
        raise HTTPException(404, "BSC Mainnet agent not found in the synchronized sample")
    return item


@api.get("/onchain/agents/{network}/{token_id}/icon", tags=["agents"])
async def onchain_agent_icon(network: str, token_id: int, request: Request):
    # A cache miss makes us fetch from a host named in third-party metadata, so
    # this path is metered like the other outbound ones.
    icon_limiter.check(client_key(request))
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    content, content_type, is_source = await get_agent_icon(db, chain_id, token_id)
    return Response(content=content, media_type=content_type, headers={
        "Cache-Control": "public, max-age=86400",
        "X-Agent-Icon-Source": "8004scan" if is_source else "generated-fallback",
    })


@api.get("/onchain/feedbacks", response_model=list[ScanFeedback], tags=["agents"])
async def list_onchain_feedbacks(network: str = "mainnet", agent_id: str | None = None):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    query: dict = {"chain_id": chain_id}
    if agent_id:
        query["agent_id"] = agent_id
    return await db.scan_feedbacks.find(query, {"_id": 0, "raw_8004scan": 0}).sort("submitted_at", -1).to_list(100)


@api.get("/my-agents/{address}", tags=["agents"])
async def my_agents(address: str, network: str = "mainnet"):
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
        raise HTTPException(400, "A valid EVM wallet address is required")
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id, is_testnet = (97, True) if network == "testnet" else (56, False)
    try:
        rows, pagination = await Scan8004Client().owned_agents(address)
        filtered = [row for row in rows if row.get("chain_id") == chain_id and row.get("is_testnet") is is_testnet]
        items = []
        for raw in filtered:
            item = public_projection(raw, chain_id, is_testnet)
            items.append(item)
            await db.scan_agents.update_one(
                {"chain_id": chain_id, "token_id": item["token_id"]},
                {"$set": {**item, "raw_8004scan": raw, "synced_at": now_iso()}},
                upsert=True,
            )
        return {"items": items, "total": len(items), "upstream_total": pagination.get("total", len(items)), "network": network, "owner_address": address, "source": "8004scan"}
    except Scan8004Error:
        cached = await db.scan_agents.find({"chain_id": chain_id, "owner_address": {"$regex": f"^{re.escape(address)}$", "$options": "i"}}, {"_id": 0, "raw_8004scan": 0, "raw_8004scan_detail": 0}).to_list(100)
        return {"items": cached, "total": len(cached), "upstream_total": None, "network": network, "owner_address": address, "source": "last_known_good", "degraded": True}


@api.get("/onchain/agent-details/{network}/{token_id}", tags=["agents"])
async def onchain_agent_detail(network: str, token_id: int):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id, is_testnet = (97, True) if network == "testnet" else (56, False)
    raw = None
    source = "8004scan_live"
    try:
        client = Scan8004Client()
        raw = await client.agent_detail(chain_id, token_id)
        feedbacks = [feedback_projection(row) for row in await client.agent_feedbacks(chain_id, token_id)]
        summary = public_projection(raw, chain_id, is_testnet)
        await db.scan_agents.update_one(
            {"chain_id": chain_id, "token_id": token_id},
            {"$set": {**summary, "raw_8004scan": raw, "raw_8004scan_detail": raw, "synced_at": now_iso()}},
            upsert=True,
        )
    except Scan8004Error:
        cached = await db.scan_agents.find_one({"chain_id": chain_id, "token_id": token_id}, {"_id": 0})
        if not cached:
            raise HTTPException(404, "Agent not found")
        raw = cached.get("raw_8004scan_detail") or cached.get("raw_8004scan")
        feedback_rows = await db.scan_feedbacks.find({"chain_id": chain_id, "agent_id": raw.get("agent_id")}, {"_id": 0, "raw_8004scan": 0}).sort("submitted_at", -1).to_list(20)
        feedbacks = [feedback_projection(row) for row in feedback_rows]
        source = "last_known_good"
    return {"agent": detail_projection(raw), "feedbacks": feedbacks, "source": source, "fetched_at": now_iso()}


BLOCKED_TERMS = ("private key", "seed phrase", "recovery phrase", "approve token", "unlimited approval", "execute swap", "sign for me")


@api.post("/tasks", response_model=TaskRecord, status_code=201, tags=["tasks"])
async def create_task(payload: TaskCreate, request: Request):
    # Creating a task is what leads to calling a third-party agent, so the
    # ceiling sits here rather than on the read paths a judge browses.
    task_limiter.check(client_key(request))
    text = f"{payload.objective} {payload.constraints}".lower()
    blocked = next((term for term in BLOCKED_TERMS if term in text), None)
    if blocked:
        raise HTTPException(422, f"Unsafe request rejected: '{blocked}' is outside the research-only schema")
    stamp, task_id = now_iso(), str(uuid.uuid4())
    extra: dict = {}
    if payload.agent_id.startswith("b402-"):
        resource = await db.b402_resources.find_one({"id": payload.agent_id}, {"_id": 0})
        if not resource:
            raise HTTPException(404, "Agent not found")
        # No price yet: the merchant quotes it in its 402 response at run time.
        agent_id, agent_name, price = resource["id"], resource["host"], None
    elif payload.agent_id.startswith("bsc-"):
        # An onchain 8004scan identity. Activatable only if it publishes a
        # callable endpoint; resolve it now so run has something to call.
        agent = await db.scan_agents.find_one({"id": payload.agent_id}, {"_id": 0, "raw_8004scan": 0})
        if not agent:
            raise HTTPException(404, "Agent not found")
        endpoint = agent.get("agent_endpoint")
        kind = agent.get("endpoint_kind")
        if not endpoint:
            detail = await _resolve_endpoint(agent)
            if not detail:
                raise HTTPException(409, "This agent publishes no callable endpoint, so it cannot be activated.")
            kind, endpoint = detail
        agent_id, agent_name, price = agent["id"], agent["name"], None
        # Carried so a URL registered as a template can be resolved to this
        # agent at run time, exactly as the probe resolved it.
        extra = {"agent_endpoint": endpoint, "endpoint_kind": kind, "agent_token_id": agent["token_id"]}
    else:
        raise HTTPException(404, "No such agent. Hire an onchain agent (bsc-...) or a b402 service.")
    task = {"id": task_id, "agent_id": agent_id, "agent_name": agent_name, "objective": payload.objective, "constraints": payload.constraints, "wallet_address": payload.wallet_address, "state": "created", "estimated_price_usd": price, "payment_terms": None, "settlement": None, "result_preview": None, "quote_id": None, "quote_expires_at": None, "tx_hash": None, "result": None, "created_at": stamp, "updated_at": stamp, **extra}
    await db.tasks.insert_one(task.copy())
    await audit(task_id, "task.created", "Research task accepted; no payment or agent execution has occurred.")
    return task


@api.get("/tasks/{task_id}", response_model=TaskDetail, tags=["tasks"])
async def get_task(task_id: str):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    events = await db.audit_events.find({"task_id": task_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    return TaskDetail(task=task, audit_events=events)


async def _resolve_endpoint(agent: dict) -> tuple[str, str] | None:
    """Fetch an onchain agent's detail and return (kind, url) of a live endpoint."""
    try:
        detail = await Scan8004Client().agent_detail(agent["chain_id"], agent["token_id"])
    except Scan8004Error:
        detail = agent.get("raw_8004scan_detail") or {}
    return agent_client.pick_endpoint(detail)


async def _b402_task(task_id: str) -> tuple[dict, dict]:
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    resource = await db.b402_resources.find_one({"id": task["agent_id"]}, {"_id": 0})
    if not resource:
        raise HTTPException(409, "This task is not attached to a b402 resource")
    return task, resource


def _call_params(task: dict, resource: dict) -> dict:
    return {resource.get("query_param") or "query": task["objective"]}


@api.post("/tasks/{task_id}/run", tags=["tasks"])
async def run_task(task_id: str, request: Request):
    run_limiter.check(client_key(request))
    """Run the task against its agent. Onchain agents are called directly; b402
    resources go through the payment challenge."""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    if task["state"] not in ("created", "payment_pending"):
        raise HTTPException(409, f"Task is already {task['state']}")
    if task.get("agent_endpoint"):
        return await _run_onchain_agent(task)
    return await _run_b402(task_id, task)


async def _run_onchain_agent(task: dict) -> dict:
    task_id = task["id"]
    try:
        result = await agent_client.call_agent(
            task["endpoint_kind"], task["agent_endpoint"], task["objective"],
            task.get("agent_token_id"),
            # The connected wallet, so read-only tools can answer about the
            # user's own position instead of the protocol in the abstract.
            task.get("wallet_address"))
    except agent_client.AgentPaymentRequired:
        # A paying onchain agent (e.g. an x402 A2A endpoint). Its settlement may
        # be off-BNB-Chain, so it is surfaced honestly rather than half-charged.
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "payment_pending", "updated_at": now_iso()}})
        await audit(task_id, "payment.required", "This agent requires payment through its own x402 endpoint; direct settlement is not yet wired.")
        raise HTTPException(409, "This agent charges through its own x402 endpoint, which AgentDock does not settle yet.")
    except agent_client.AgentRejected as exc:
        # The agent is reachable and simply refused. Saying "completed" here and
        # showing its error text as the result is how a failure gets dressed up
        # as an answer, so the refusal is recorded as exactly that.
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "state": "failed", "result_preview": str(exc), "failure_reason": exc.reason, "updated_at": now_iso()}})
        await audit(task_id, "run.rejected", f"The agent answered but did not do the work: {exc}")
        detail = ("This agent needs its own credential, which AgentDock does not hold."
                  if exc.reason == "auth" else str(exc))
        raise HTTPException(UPSTREAM_FAILED, detail) from exc
    except agent_client.AgentCallError as exc:
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "state": "failed", "result_preview": str(exc), "failure_reason": "unreachable", "updated_at": now_iso()}})
        await audit(task_id, "run.failed", f"Agent endpoint could not be reached safely: {exc}")
        raise HTTPException(UPSTREAM_FAILED, str(exc)) from exc
    output = result.get("output") or ""
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "state": "completed", "result": result, "result_preview": output[:1200],
        "estimated_price_usd": 0.0, "updated_at": now_iso()}})
    await audit(task_id, "run.completed", f"Agent executed over {result.get('transport', 'its endpoint')} and returned a result. No payment was required.")
    return {"state": "completed", "paid": False, "result_preview": output[:1200], "transport": result.get("transport")}


async def _run_b402(task_id: str, task: dict) -> dict:
    resource = await db.b402_resources.find_one({"id": task["agent_id"]}, {"_id": 0})
    if not resource:
        raise HTTPException(409, "This task is not attached to a runnable agent")
    try:
        challenge, response, method = await b402.fetch_challenge(resource["resource"], params=_call_params(task, resource))
    except b402.B402Error as exc:
        await audit(task_id, "run.failed", f"Agent endpoint could not be reached safely: {exc}")
        raise HTTPException(UPSTREAM_FAILED, str(exc)) from exc

    if response.status_code < 400 and not challenge:
        body = response.text[:4000]
        # A redirect, a 204, or an empty body is not an answer. Accepting any
        # sub-400 status here turned a moved endpoint into a completed task with
        # nothing in it — and /run then refused to retry it.
        if response.status_code >= 300 or not body.strip():
            await audit(task_id, "run.failed", f"Agent returned HTTP {response.status_code} with neither payment terms nor content.")
            raise HTTPException(UPSTREAM_FAILED, f"Agent returned HTTP {response.status_code} with neither payment terms nor a result")
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "completed", "result": {"body": body}, "result_preview": body[:600], "estimated_price_usd": 0.0, "updated_at": now_iso()}})
        await audit(task_id, "run.completed", "Agent answered without requesting payment; no signature was requested.")
        return {"state": "completed", "paid": False, "result_preview": body[:600]}

    if not challenge:
        await audit(task_id, "run.failed", f"Agent returned HTTP {response.status_code} without payment terms.")
        raise HTTPException(UPSTREAM_FAILED, f"Agent returned HTTP {response.status_code} without payment terms")

    try:
        accept = b402.select_bsc_eip3009(challenge)
        terms = b402.describe_terms(accept)
    except b402.PaymentRefused as exc:
        await audit(task_id, "payment.refused", str(exc))
        raise HTTPException(409, str(exc)) from exc
    except b402.B402Error as exc:
        raise HTTPException(UPSTREAM_FAILED, str(exc)) from exc

    await db.tasks.update_one({"id": task_id}, {"$set": {"state": "payment_pending", "payment_terms": terms, "b402_accept": accept, "b402_method": method, "estimated_price_usd": terms["amount_tokens"], "updated_at": now_iso()}})
    await audit(task_id, "payment.quoted", f"Agent requires {terms['amount_tokens']:g} {terms['asset_name']} on BNB Chain. Nothing is signed until you approve it in your wallet.")
    return {"state": "payment_pending", "paid": True, "terms": terms}


@api.post("/tasks/{task_id}/authorize", tags=["tasks"])
async def authorize_task(task_id: str, payload: AuthorizeRequest):
    """Return EIP-712 typed data for the user's wallet. No key is held here."""
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", payload.payer):
        raise HTTPException(422, "A valid EVM payer address is required")
    task, _ = await _b402_task(task_id)
    if task["state"] != "payment_pending":
        raise HTTPException(409, f"Task is {task['state']}, not awaiting payment")
    accept = task.get("b402_accept")
    if not accept:
        raise HTTPException(409, "Run the task first to obtain the merchant's terms")

    # Minted fresh on every attempt: the merchant's window is short, and a reused
    # nonce would let the same authorization be replayed.
    now = int(datetime.now(timezone.utc).timestamp())
    valid_before = now + int(accept.get("maxTimeoutSeconds") or b402.DEFAULT_VALIDITY_SECONDS)
    nonce = "0x" + uuid.uuid4().hex + uuid.uuid4().hex
    typed_data = b402.build_typed_data(accept, payload.payer, now - 5, valid_before, nonce)
    await db.tasks.update_one({"id": task_id}, {"$set": {"b402_authorization": typed_data["message"], "wallet_address": payload.payer, "updated_at": now_iso()}})
    await audit(task_id, "payment.authorization_prepared", "Payment authorization prepared for wallet signature.")
    return {"typed_data": typed_data, "terms": task.get("payment_terms"), "expires_at": datetime.fromtimestamp(valid_before, timezone.utc).isoformat()}


@api.post("/tasks/{task_id}/pay", tags=["tasks"])
async def pay_task(task_id: str, payload: PayRequest):
    """Replay the call with the user's signature attached."""
    if not re.fullmatch(r"0x[a-fA-F0-9]{130}", payload.signature):
        raise HTTPException(422, "A valid 65-byte signature is required")
    task, resource = await _b402_task(task_id)
    accept, authorization = task.get("b402_accept"), task.get("b402_authorization")
    if not accept or not authorization:
        raise HTTPException(409, "Prepare the payment authorization first")

    # Idempotency: only a task still awaiting payment may move to paid, so a
    # double submit cannot pay twice.
    moved = await db.tasks.update_one({"id": task_id, "state": "payment_pending"}, {"$set": {"state": "paid", "updated_at": now_iso()}})
    if moved.modified_count != 1:
        raise HTTPException(409, f"Task is {task['state']}, not awaiting payment")
    await audit(task_id, "payment.submitted", "Signed payment authorization submitted to the agent.")

    header = b402.build_payment_header(accept, payload.signature, authorization)
    try:
        response = await b402.call_paid(resource["resource"], header, method=task.get("b402_method", "GET"), params=_call_params(task, resource))
    except b402.PaymentNotSent as exc:
        # The authorization was never presented, so it is still unspent. Returning
        # the task to payment_pending is what makes the attempt retryable instead
        # of stranding it in "paid" with nothing paid.
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "payment_pending", "updated_at": now_iso()}})
        await audit(task_id, "payment.not_sent", f"Nothing was charged: {exc}. The authorization is unused and can be resubmitted.")
        raise HTTPException(UPSTREAM_FAILED, f"{exc}. You can try again.") from exc
    except b402.PaymentUncertain as exc:
        # Sent but unanswered. Claiming either outcome would be a guess about the
        # user's money, so it is flagged for a human instead.
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "manual_resolution", "updated_at": now_iso()}})
        await audit(task_id, "payment.uncertain", f"{exc}. Check the payer address on BscScan before retrying.")
        raise HTTPException(UPSTREAM_FAILED, f"{exc}. Check your wallet on BscScan before retrying.") from exc
    except b402.B402Error as exc:
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "failed", "updated_at": now_iso()}})
        await audit(task_id, "run.failed", f"Paid call failed: {exc}")
        raise HTTPException(UPSTREAM_FAILED, str(exc)) from exc

    try:
        settlement = b402.decode_settlement(response)
        settlement_error = None
    except b402.B402Error as exc:
        settlement, settlement_error = None, str(exc)
    if response.status_code >= 400:
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "failed", "settlement": settlement, "updated_at": now_iso()}})
        await audit(task_id, "payment.rejected", f"Agent rejected the payment with HTTP {response.status_code}.")
        raise HTTPException(402, {"message": "Agent rejected the payment", "status": response.status_code, "settlement": settlement, "body": response.text[:600]})

    # A 2xx says the merchant served the content, not that the money moved: the
    # facilitator reports that separately in the payment-response header. Reading
    # only the status showed a green "settled" task with no transaction to check.
    if settlement is not None and settlement.get("success") is False:
        reason = settlement.get("errorReason") or "the facilitator did not settle the payment"
        await db.tasks.update_one({"id": task_id}, {"$set": {"state": "failed", "settlement": settlement, "updated_at": now_iso()}})
        await audit(task_id, "payment.unsettled", f"The agent served a response but the payment did not settle: {reason}.")
        raise HTTPException(402, f"The payment did not settle: {reason}")

    body = response.text[:4000]
    tx_hash = (settlement or {}).get("transaction") or None
    settled = bool(settlement and settlement.get("success") is not False and tx_hash)
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "state": "completed", "result": {"body": body}, "result_preview": body[:600],
        "settlement": settlement, "settlement_verified": settled, "settlement_note": settlement_error,
        "tx_hash": tx_hash, "updated_at": now_iso()}})
    await audit(task_id, "run.completed", (
        f"Agent executed and returned a result; the facilitator settled it in transaction {tx_hash}."
        if settled else
        "Agent executed and returned a result. It reported no settlement receipt, so the on-chain transfer is unconfirmed."))
    return {"state": "completed", "result_preview": body[:600], "settlement": settlement,
            "settlement_verified": settled, "tx_hash": tx_hash}


@api.post("/tasks/{task_id}/quote", tags=["tasks"])
async def create_quote(task_id: str, payload: QuoteRequest):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", payload.payer):
        raise HTTPException(422, "A valid EVM payer address is required")
    if not b402_merchant.ready:
        await audit(task_id, "quote.blocked", "Binance B402 partner configuration is not active; no payment was requested.")
        raise HTTPException(UPSTREAM_UNAVAILABLE, "Binance B402 is not configured. Payment remains disabled and no wallet signature is requested.")
    quote_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    try:
        requirements = await b402_merchant.supported()
    except B402Unavailable as exc:
        raise HTTPException(UPSTREAM_UNAVAILABLE, str(exc)) from exc
    await db.tasks.update_one({"id": task_id, "state": "created"}, {"$set": {"quote_id": quote_id, "quote_expires_at": expires_at, "wallet_address": payload.payer, "updated_at": now_iso()}})
    return {"quote_id": quote_id, "chain_id": CHAIN_ID, "expires_at": expires_at, "amount_usd": task["estimated_price_usd"], "payment_requirements": requirements}


@api.post("/tasks/{task_id}/feedback", tags=["tasks"])
async def feedback(task_id: str, payload: FeedbackRequest):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    if task["state"] != "completed":
        raise HTTPException(409, "Feedback is accepted only after completion")
    await db.feedback.insert_one({"id": str(uuid.uuid4()), "task_id": task_id, **payload.model_dump(), "created_at": now_iso()})
    await audit(task_id, "feedback.recorded", "User feedback recorded as one signal, not standalone proof.")
    return {"status": "recorded"}


app.include_router(api)
# An unset CORS_ORIGINS used to become [""], which allows nothing while looking
# configured — the browser reports only an opaque CORS failure. Fail loudly at
# boot instead, and never fall back to "*" with credentials enabled.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if not _cors_origins:
    raise RuntimeError("CORS_ORIGINS must list the frontend origins, comma separated")
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=_cors_origins,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-Admin-Token"])


@app.on_event("shutdown")
async def shutdown():
    client.close()