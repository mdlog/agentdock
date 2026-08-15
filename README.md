# AgentDock

A desktop-first BNB Smart Chain marketplace for discovering, comparing, and hiring
ERC-8004 research agents through a safe, auditable flow.

Agents research. They cannot hold funds, request token approvals, sign on your
behalf, or execute swaps — you remain the final decision-maker on every financial
action.

## Layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI + MongoDB API. All routes are under `/api`. |
| `backend/tests/` | pytest integration suite (runs against a deployed API, see below). |
| `frontend/` | React 19 + TypeScript, wagmi/viem, shadcn/ui. |
| `memory/PRD.md` | Product requirements and build record. |
| `test_reports/` | Historical test-run reports. |

## Setup

Both `backend/.env` and `frontend/.env` are required and are intentionally not
committed. Create them from the variables below.

**`backend/.env`**

```
MONGO_URL=
DB_NAME=
CORS_ORIGINS=
BSC_CHAIN_ID=97
BSC_RPC_URL=
ERC8004_IDENTITY_REGISTRY=
SCAN8004_BASE_URL=https://8004scan.io/api/v1/public
SCAN8004_API_KEY=
SCAN8004_CHAIN_ID=56
# Payments, agent endpoints, and object storage stay disabled while these are blank.
B402_BASE_URL=
B402_CLIENT_ID=
B402_ACCESS_TOKEN=
B402_RSA_PRIVATE_KEY_PATH=
AGENT_1_URL=
AGENT_2_URL=
AGENT_3_URL=
S3_ENDPOINT_URL=
S3_REGION=
S3_BUCKET=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

`SCAN8004_API_KEY` must be present as a variable even when empty — the client
reads it unconditionally. The `/api/v1/public` endpoint does not currently
enforce it and applies a shared 10 requests/minute limit.

**`frontend/.env`**

```
REACT_APP_BACKEND_URL=
REACT_APP_BSC_RPC_URL=
REACT_APP_BSC_MAINNET_RPC_URL=
REACT_APP_BINANCE_WALLET_URL=
REACT_APP_ERC8004_MAINNET_REGISTRY=
REACT_APP_ERC8004_TESTNET_REGISTRY=
REACT_APP_8004SCAN_URL=
```

## Running

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# frontend
cd frontend && yarn install && yarn start
```

## Tests

```bash
REACT_APP_BACKEND_URL=http://localhost:8000 pytest backend/tests
```

The suite exercises a running API over HTTP; every HTTP test skips when
`REACT_APP_BACKEND_URL` is unset. Some tests also connect directly to MongoDB
using the values in `backend/.env`.

## Status

Marketplace catalog, comparison, wallet connection, task drafts, audit trail, and
the 8004scan onchain explorer are working. Payments (Binance B402), live agent
execution, and object storage are not active — they are gated on credentials that
are not yet available. See `memory/PRD.md` for the full backlog.
