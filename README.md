# AgentDock

A marketplace for the ERC-8004 agents registered on BNB Smart Chain — where you
can find one that does a specific job, see evidence that it works, and hire it
with your own wallet.

**Live:** [agents.mdloglabs.org](https://agents.mdloglabs.org) ·
**API:** [api.mdloglabs.org](https://api.mdloglabs.org/api/health)

Agents do work and return results. They never hold your funds, request token
approvals, sign on your behalf, or execute swaps: every payment is an EIP-3009
authorization signed in your own browser, with the token, amount and recipient
shown before your wallet is asked for anything.

## The problem this exists to solve

BNB Chain's ERC-8004 registry holds **256,859 registered agents**. AgentDock
called the endpoint of every categorised one to find out how many can actually
be used:

| Verdict | Count | Meaning |
|---|---:|---|
| Live | **8** | Answered a real call. These are hireable here. |
| Not deployed | 290 | Registered; the hosting platform reports no service bound. |
| Faulty | 133 | Endpoint answers, but not usably. |
| No endpoint | 596 | Registration publishes no callable address. |
| Offline | 6 | Host did not respond. |

Only six hosts are genuinely down. The registry's problem is not fragile
infrastructure — it is mass registration with nothing behind it. Without
verification, the eight working agents are invisible among a thousand that are
not. Finding them is what this marketplace is for, and every card states what
its endpoint actually did when we called it.

## The four judged categories

| Category | Registered | Hireable now |
|---|---:|---:|
| Rebalancing | 75 | 2 |
| Grid Trading | 345 | **0** |
| Yield Optimisation | 616 | 6 |
| Health Factor Monitoring | 21 | 3 |

Grid Trading shows zero because all 345 registrations were probed and none is
callable — not a gap in our search. The marketplace says so on the category
card rather than promising 345 agents and disabling every button.

## What is real

Everything the interface claims is checked against a live source. Specifically:

- **Catalogue** — synced from 8004scan, the full BSC mainnet registry, with a
  ten-minute pass that catches new registrations.
- **Endpoint verdicts** — from real MCP `initialize` / A2A `tasks/get` probes,
  not from metadata. `activatable` means "we called it and it worked".
- **Payments** — quoted by the merchant's own HTTP 402 challenge at run time.
  No price is ever invented; the b402 Bazaar catalogue is used for discovery only.
- **Results** — whatever the agent returned. An agent that refuses is recorded
  as failed, with its own words, never as a completed task.

Not yet live: no settlement has been executed with real funds on the b402 path
(the flow is verified up to the wallet signature), and AgentDock does not itself
operate any agent.

## Architecture

```
Browser ─── wagmi/viem ──▶ user's wallet (signs; keys never leave it)
   │
   ├── agents.mdloglabs.org ── static React build (systemd: agentdock-web)
   │
   └── api.mdloglabs.org ───── FastAPI (systemd: agentdock-api)
                                 ├── MongoDB — 256k agents, tasks, audit trail
                                 ├── 8004scan — registry sync (server-side key)
                                 ├── agent endpoints — MCP / A2A, SSRF-guarded
                                 └── b402 / x402 — 402 challenge, EIP-3009
```

| Path | What it is |
|---|---|
| `backend/` | FastAPI + MongoDB. All routes under `/api`. |
| `backend/agent_client.py` | Calls and probes agent endpoints; classifies refusals. |
| `backend/b402.py` | Buyer-side b402/x402 client. Holds no keys. |
| `backend/scan8004.py` | Registry sync, category derivation. |
| `backend/guards.py` | Operator gate and per-caller rate limits. |
| `frontend/` | React 19 + TypeScript, wagmi/viem, shadcn/ui. |
| `deploy/` | systemd units and their runbook. |
| `scripts/serve_frontend.py` | Static server: SPA routing, cache headers. |
| `docs/` | Upstream bug reports filed from this work. |

## Running it

Requires Python 3.12, Node 20, and MongoDB.

```bash
# backend
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in, see below
./.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000

# frontend
cd frontend && npm install
cp .env.example .env          # REACT_APP_BACKEND_URL must point at the API
npm start                     # or: npm run build, then see deploy/README.md
```

`backend/.env` and `frontend/.env` are deliberately not committed; both
`.env.example` files list every variable with a comment on what it does. The
8004scan key is used server-side only and never reaches the browser — agent
icons are proxied rather than hot-linked, for that reason.

Maintenance endpoints (`/api/b402/sync`, `/api/onchain/sync-all`,
`/api/onchain/enrich-endpoints`) require `X-Admin-Token` matching `ADMIN_TOKEN`,
and refuse everyone when it is unset. They spend a rate-limited sponsor quota,
so they are closed by default.

## Tests

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q
```

81 unit tests cover the parts where being wrong is expensive: how an agent's
refusal is told from an answer, what a payment outcome means when the call
fails mid-flight, and the public API's guards. The suite additionally holds
integration tests that skip unless a deployed API is configured.

## Deployment

See [`deploy/README.md`](deploy/README.md). Both services run as systemd user
units bound to loopback, reached only through a Cloudflare tunnel.

## Licence

MIT — see [LICENSE](LICENSE).

## Upstream findings

Work here surfaced bugs in services this depends on; they are documented in
[`docs/`](docs/) rather than worked around silently — including 8004scan's
`X-API-Key` header being ignored in favour of `Authorization: Bearer`, and its
list route returning mixed chains when passed `chainId` instead of `chain_id`.
