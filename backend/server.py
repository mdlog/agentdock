from datetime import datetime, timedelta, timezone
import os
import re
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from integrations import ArtifactStore, B402Adapter, B402Unavailable, registry_health
from models import Agent, AgentList, AuditEvent, CompareRequest, FeedbackRequest, IntegrationReadiness, QuoteRequest, ScanAgent, ScanAgentList, ScanFeedback, TaskCreate, TaskDetail, TaskRecord
from seed_data import CATEGORIES, PANCAKE_POOLS, seed_agents
from scan8004 import Scan8004Client, Scan8004Error, detail_projection, feedback_projection, public_projection, sync_bsc_mainnet, sync_bsc_testnet, sync_feedbacks
from icon_proxy import get_agent_icon


load_dotenv()
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="AgentDock API", version="1.0.0")
api = APIRouter(prefix="/api")
b402 = B402Adapter()
artifacts = ArtifactStore()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def audit(task_id: str, event: str, detail: str) -> None:
    await db.audit_events.insert_one({"id": str(uuid.uuid4()), "task_id": task_id, "event": event, "detail": detail, "created_at": now_iso()})


@app.on_event("startup")
async def startup() -> None:
    await db.agents.create_index("id", unique=True)
    await db.tasks.create_index("id", unique=True)
    await db.audit_events.create_index([("task_id", 1), ("created_at", 1)])
    await db.payments.create_index("tx_hash", unique=True, sparse=True)
    await db.scan_agents.create_index([("chain_id", 1), ("token_id", 1)], unique=True)
    await db.scan_agents.create_index([("name", "text"), ("description", "text")])
    await db.sync_runs.create_index([("source", 1), ("chain_id", 1)], unique=True)
    await db.scan_feedbacks.create_index([("chain_id", 1), ("feedback_id", 1)], unique=True)
    await db.scan_feedbacks.create_index([("chain_id", 1), ("agent_id", 1), ("submitted_at", -1)])
    await db.scan_agent_icons.create_index([("chain_id", 1), ("token_id", 1)], unique=True)
    if await db.agents.count_documents({}) == 0:
        await db.agents.insert_many(seed_agents())
    app.state.scan_sync_task = __import__("asyncio").create_task(sync_bsc_mainnet(db))
    app.state.scan_testnet_task = __import__("asyncio").create_task(sync_bsc_testnet(db))
    app.state.scan_mainnet_feedback_task = __import__("asyncio").create_task(sync_feedbacks(db, 56, False))
    app.state.scan_testnet_feedback_task = __import__("asyncio").create_task(sync_feedbacks(db, 97, True))


@api.get("/", tags=["system"])
async def root():
    return {"message": "AgentDock API", "status": "ready"}


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
    if not b402.ready:
        notes.append("Binance B402 partner onboarding is required before payment can be enabled.")
    if not endpoints_ready:
        notes.append("Seed profiles are visible, but live agent endpoints are not configured.")
    if not artifacts.ready:
        notes.append("Result artifacts will use MongoDB fallback until object storage is configured.")
    return IntegrationReadiness(chain_id=97, registry_configured=bool(os.environ.get("ERC8004_IDENTITY_REGISTRY")), rpc_reachable=rpc_ok, registry_has_code=code_ok, b402_ready=b402.ready, agent_endpoints_ready=endpoints_ready, object_storage_ready=artifacts.ready, storage_mode="object_storage" if artifacts.ready else "mongodb_fallback", notes=notes)


@api.get("/integrations/8004scan/status", tags=["system"])
async def scan_status(network: str = "mainnet"):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id = 97 if network == "testnet" else 56
    status = await db.sync_runs.find_one({"source": "8004scan", "chain_id": chain_id}, {"_id": 0})
    feedback_count = await db.scan_feedbacks.count_documents({"chain_id": chain_id})
    result = status or {"status": "never_run", "source": "8004scan", "chain_id": chain_id, "is_testnet": network == "testnet"}
    return {**result, "feedback_sample": feedback_count}


@api.get("/onchain/agents", response_model=ScanAgentList, tags=["agents"])
async def list_onchain_agents(
    network: str = "mainnet",
    search: str = "",
    protocol: str | None = None,
    x402: bool | None = None,
    verified: bool | None = None,
    sort: str = "score",
):
    if network not in ("mainnet", "testnet"):
        raise HTTPException(400, "network must be mainnet or testnet")
    chain_id, is_testnet = (97, True) if network == "testnet" else (56, False)
    query: dict = {"chain_id": chain_id, "is_testnet": is_testnet}
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
    sort_map = {"score": ("total_score", -1), "rank": ("rank", 1), "feedback": ("total_feedbacks", -1), "newest": ("created_at", -1)}
    field, direction = sort_map.get(sort, sort_map["score"])
    items = await db.scan_agents.find(query, {"_id": 0, "raw_8004scan": 0}).sort(field, direction).to_list(100)
    return ScanAgentList(items=items, total=len(items), chain_id=chain_id, is_testnet=is_testnet)


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
async def onchain_agent_icon(network: str, token_id: int):
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


@api.get("/agents", response_model=AgentList, tags=["agents"])
async def list_agents(
    search: str = "",
    category: str | None = None,
    status: str | None = None,
    max_price: float | None = Query(default=None, ge=0),
    sort: str = "reputation",
):
    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": re.escape(search), "$options": "i"}},
            {"tagline": {"$regex": re.escape(search), "$options": "i"}},
            {"capabilities": {"$regex": re.escape(search), "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if status:
        query["status"] = status
    if max_price is not None:
        query["price_usd"] = {"$lte": max_price}
    sort_map = {"reputation": ("metrics.reputation_score", -1), "price_low": ("price_usd", 1), "latency": ("metrics.latency_sec", 1), "volume": ("metrics.task_volume", -1)}
    field, direction = sort_map.get(sort, sort_map["reputation"])
    items = await db.agents.find(query, {"_id": 0}).sort(field, direction).to_list(100)
    return AgentList(items=items, total=len(items), categories=CATEGORIES)


@api.get("/agents/{agent_id}", response_model=Agent, tags=["agents"])
async def get_agent(agent_id: str):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@api.post("/agents/compare", response_model=list[Agent], tags=["agents"])
async def compare_agents(payload: CompareRequest):
    if len(set(payload.agent_ids)) != len(payload.agent_ids):
        raise HTTPException(400, "Choose distinct agents")
    agents = await db.agents.find({"id": {"$in": payload.agent_ids}}, {"_id": 0}).to_list(3)
    ordered = sorted(agents, key=lambda item: payload.agent_ids.index(item["id"]))
    if len(ordered) != len(payload.agent_ids):
        raise HTTPException(404, "One or more agents were not found")
    return ordered


@api.get("/pancakeswap/pools", tags=["pancakeswap"])
async def pancake_pools():
    return {"items": PANCAKE_POOLS, "mode": "reference_snapshot", "read_only": True}


BLOCKED_TERMS = ("private key", "seed phrase", "recovery phrase", "approve token", "unlimited approval", "execute swap", "sign for me")


@api.post("/tasks", response_model=TaskRecord, status_code=201, tags=["tasks"])
async def create_task(payload: TaskCreate):
    text = f"{payload.objective} {payload.constraints}".lower()
    blocked = next((term for term in BLOCKED_TERMS if term in text), None)
    if blocked:
        raise HTTPException(422, f"Unsafe request rejected: '{blocked}' is outside the research-only schema")
    agent = await db.agents.find_one({"id": payload.agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(404, "Agent not found")
    if agent["status"] != "active":
        raise HTTPException(409, "Agent is currently offline")
    stamp, task_id = now_iso(), str(uuid.uuid4())
    task = {"id": task_id, "agent_id": agent["id"], "agent_name": agent["name"], "objective": payload.objective, "constraints": payload.constraints, "wallet_address": payload.wallet_address, "state": "created", "estimated_price_usd": agent["price_usd"], "quote_id": None, "quote_expires_at": None, "tx_hash": None, "result": None, "created_at": stamp, "updated_at": stamp}
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


@api.post("/tasks/{task_id}/quote", tags=["tasks"])
async def create_quote(task_id: str, payload: QuoteRequest):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", payload.payer):
        raise HTTPException(422, "A valid EVM payer address is required")
    if not b402.ready:
        await audit(task_id, "quote.blocked", "Binance B402 partner configuration is not active; no payment was requested.")
        raise HTTPException(503, "Binance B402 is not configured. Payment remains disabled and no wallet signature is requested.")
    quote_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    try:
        requirements = await b402.supported()
    except B402Unavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    await db.tasks.update_one({"id": task_id, "state": "created"}, {"$set": {"quote_id": quote_id, "quote_expires_at": expires_at, "wallet_address": payload.payer, "updated_at": now_iso()}})
    return {"quote_id": quote_id, "chain_id": 97, "expires_at": expires_at, "amount_usd": task["estimated_price_usd"], "payment_requirements": requirements}


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
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "").split(","), allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown():
    client.close()