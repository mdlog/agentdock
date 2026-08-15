# Deploying AgentDock

The hackathon requires a **functional, publicly accessible marketplace during
judging**. This is what it takes to get there. Nothing in the images is secret;
all credentials come from the environment at run time (backend) or build time
(frontend).

## The four moving parts

| Part | What it is | Where it can live |
|---|---|---|
| MongoDB | agent catalogue, tasks, icons cache | MongoDB Atlas (free tier is enough) |
| Backend | FastAPI, reads Mongo + 8004scan + b402 | Render / Fly.io / Railway (a container host) |
| Frontend | static CRA bundle | Vercel / Netlify / any static host or the nginx image |
| RPC + 8004scan key | external services | Alchemy/QuickNode BNB endpoint; 8004scan Pro key |

The one non-obvious constraint: **Create React App bakes `REACT_APP_*` at build
time**, so the frontend must be rebuilt whenever the backend URL changes. It
cannot be switched at runtime.

## Option A — one host with Docker Compose (fastest)

Good for a single VPS or for verifying the build locally.

```bash
# Public addresses the *browser* will use. On a server, use its host/domain.
export PUBLIC_URL="https://your-frontend.example"        # where users load the app
export BACKEND_PUBLIC_URL="https://your-backend.example" # where the browser calls the API
export BSC_RPC_URL="https://bnb-mainnet.g.alchemy.com/v2/<key>"
export SCAN8004_API_KEY="<your 8004scan Pro key>"

docker compose up -d --build
```

- Frontend on `:3100`, backend on `:8000`, Mongo internal only.
- After it is up, trigger the full catalogue sync once:
  `curl -X POST "$BACKEND_PUBLIC_URL/api/onchain/sync-all?network=mainnet"`
- `CORS_ORIGINS` is set to `PUBLIC_URL`; the frontend is built against
  `BACKEND_PUBLIC_URL`. If the browser calls the API from a different origin than
  `CORS_ORIGINS`, requests are blocked — keep these consistent.

## Option B — hosted split (recommended for judging)

1. **MongoDB Atlas** — create a free M0 cluster, get the `mongodb+srv://…` URL.
2. **Backend** on Render/Fly/Railway — deploy `backend/` (it has a Dockerfile). Set env:
   `MONGO_URL` (the Atlas URL), `DB_NAME=agentdock`, `BSC_CHAIN_ID=56`,
   `BSC_RPC_URL`, `ERC8004_IDENTITY_REGISTRY=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`,
   `SCAN8004_BASE_URL=https://8004scan.io/api/v1/public`, `SCAN8004_API_KEY`,
   `SCAN8004_CHAIN_ID=56`, and `CORS_ORIGINS=<your frontend URL>`.
3. **Frontend** on Vercel/Netlify — build `frontend/` with
   `REACT_APP_BACKEND_URL=<your backend URL>` and the other `REACT_APP_*` from
   `frontend/.env.example`. Build command `yarn build`, output `build/`.
4. After the backend is live, run the sync once (curl above). It takes tens of
   minutes; the ranked first page is usable immediately.

## After deploying — verify the judged journey over the PUBLIC url

- Marketplace loads, four category cards show live counts.
- Click a category → the grid narrows to real agents in it (Rebalancing, Grid
  Trading, Yield Optimisation, Health Factor Monitoring).
- Yield → hireable HYRE services appear; open one → create task → get price →
  the payment terms panel renders (signing needs a funded wallet on BNB Chain).
- `GET <backend>/api/categories` returns four categories with non-zero counts.
- `GET <backend>/api/integrations/readiness` shows `chain_id: 56`,
  `rpc_reachable: true`.

## Secrets checklist before going public

- `backend/.env` and `frontend/.env` are gitignored — never commit them.
- The frontend bundle is public by definition; put no secret in `REACT_APP_*`.
- Rotate any key that has ever been committed before relying on it.
