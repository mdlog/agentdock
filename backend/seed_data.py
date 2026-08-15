from datetime import datetime, timezone
import os


CATEGORIES = ["Yield Research", "Pool Analysis", "Risk Intelligence", "Market Research"]


AGENT_BLUEPRINTS = [
    ("yield-scout", "Yield Scout", "Ranks sustainable BSC yield", "Yield Research", ["APY ranking", "IL analysis", "Pool screening"], 1.20),
    ("pool-lens", "Pool Lens", "Explains pool quality before you deposit", "Pool Analysis", ["Liquidity depth", "Volume trends", "Fee efficiency"], 0.90),
    ("risk-radar", "Risk Radar", "Flags contract and market risk", "Risk Intelligence", ["Token risk", "Contract signals", "Concentration"], 1.50),
    ("delta-research", "Delta Research", "Turns market signals into a clear brief", "Market Research", ["Market brief", "Catalysts", "Scenario analysis"], 1.10),
    ("cake-yield-map", "Cake Yield Map", "Maps PancakeSwap opportunities", "Yield Research", ["PancakeSwap", "Farm comparison", "Reward quality"], 1.35),
    ("liquidity-watch", "Liquidity Watch", "Tracks liquidity migration", "Pool Analysis", ["Liquidity depth", "Flow tracking", "Pool screening"], 0.80),
    ("vault-sentinel", "Vault Sentinel", "Reviews vault strategy risk", "Risk Intelligence", ["Vault risk", "Exposure map", "Protocol review"], 1.75),
    ("bnb-macro", "BNB Macro", "Connects ecosystem news to market structure", "Market Research", ["Market brief", "BNB ecosystem", "Catalysts"], 1.00),
    ("apy-truth", "APY Truth", "Separates emissions from organic yield", "Yield Research", ["APY ranking", "Reward quality", "Sustainability"], 1.45),
    ("pair-profiler", "Pair Profiler", "Builds a compact LP pair dossier", "Pool Analysis", ["Pair analysis", "IL analysis", "Volume trends"], 0.95),
    ("token-guard", "Token Guard", "Screens tokens before research", "Risk Intelligence", ["Token risk", "Holder concentration", "Liquidity locks"], 0.70),
    ("signal-desk", "Signal Desk", "Produces evidence-linked market notes", "Market Research", ["Market brief", "Source citations", "Scenario analysis"], 1.25),
    ("farm-compare", "Farm Compare", "Compares farm rewards net of risk", "Yield Research", ["Farm comparison", "APY ranking", "Protocol review"], 1.60),
    ("depth-check", "Depth Check", "Measures execution depth without trading", "Pool Analysis", ["Liquidity depth", "Price impact", "Route research"], 1.05),
    ("protocol-facts", "Protocol Facts", "Verifies protocol claims against evidence", "Risk Intelligence", ["Protocol review", "Claim verification", "Source citations"], 1.30),
    ("trend-canvas", "Trend Canvas", "Summarizes BSC sector momentum", "Market Research", ["Trend analysis", "Sector map", "Catalysts"], 0.85),
    ("stable-yield", "Stable Yield", "Finds lower-volatility yield candidates", "Yield Research", ["Stablecoin pools", "APY ranking", "Risk filters"], 1.15),
    ("volume-pulse", "Volume Pulse", "Finds volume and fee inflections", "Pool Analysis", ["Volume trends", "Fee efficiency", "Flow tracking"], 0.75),
    ("exposure-map", "Exposure Map", "Maps correlated protocol exposure", "Risk Intelligence", ["Exposure map", "Dependency risk", "Concentration"], 1.80),
    ("research-minute", "Research Minute", "Creates a fast decision memo", "Market Research", ["Market brief", "Pros and cons", "Source citations"], 0.60),
]


def seed_agents() -> list[dict]:
    registry = os.environ.get("ERC8004_IDENTITY_REGISTRY", "")
    chain_id = int(os.environ.get("BSC_CHAIN_ID", "56"))
    stamp = datetime.now(timezone.utc).isoformat()
    agents = []
    for idx, (agent_id, name, tagline, category, capabilities, price) in enumerate(AGENT_BLUEPRINTS, start=1):
        success = round(96.8 - (idx % 7) * 1.1, 1)
        uptime = round(99.7 - (idx % 5) * 0.6, 1)
        latency = 28 + (idx * 13) % 105
        volume = 84 + idx * 37
        recency = round(98 - (idx % 6) * 2.2, 1)
        feedback = round(94 - (idx % 4) * 2.5, 1)
        reputation = round(success * .35 + uptime * .2 + recency * .15 + feedback * .15 + min(volume / 10, 100) * .1 + max(0, 100-latency/2) * .05, 1)
        agents.append({
            "id": agent_id,
            "name": name,
            "tagline": tagline,
            "description": f"{tagline}. Produces a read-only research report with assumptions, evidence, and risks. It never requests token approval or executes a swap.",
            "category": category,
            "capabilities": capabilities,
            "price_usd": price,
            "status": "offline" if idx in (12, 19) else "active",
            "metrics": {"success_rate": success, "uptime_pct": uptime, "latency_sec": latency, "task_volume": volume, "recency_score": recency, "feedback_score": feedback, "reputation_score": reputation},
            "identity": {"chain_id": chain_id, "registry": registry, "agent_id": idx, "metadata_verified": idx % 4 != 0, "endpoint_verified": False, "source": "ERC-8004 seed pending sync"},
            "output_schema": ["Summary", "Evidence", "Risk flags", "Recommendation"],
            "updated_at": stamp,
        })
    return agents


PANCAKE_POOLS = [
    {"id": "wbnb-usdt", "pair": "WBNB / USDT", "fee_tier": "0.25%", "liquidity_usd": 18400000, "volume_24h_usd": 7200000, "apr": 14.8, "risk": "Medium", "source": "Reference snapshot — connect PancakeSwap data adapter for live values"},
    {"id": "usdt-usdc", "pair": "USDT / USDC", "fee_tier": "0.01%", "liquidity_usd": 12100000, "volume_24h_usd": 4900000, "apr": 5.2, "risk": "Low", "source": "Reference snapshot — connect PancakeSwap data adapter for live values"},
    {"id": "cake-wbnb", "pair": "CAKE / WBNB", "fee_tier": "0.25%", "liquidity_usd": 8900000, "volume_24h_usd": 3100000, "apr": 24.6, "risk": "High", "source": "Reference snapshot — connect PancakeSwap data adapter for live values"},
]