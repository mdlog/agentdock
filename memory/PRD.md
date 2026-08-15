# AgentDock — Product Requirements & Build Record

**Last updated:** 2026-08-15

## Original problem statement

AgentDock is a desktop-first BNB Agent Marketplace for discovering, comparing, paying, and running ERC-8004 agents through a safe, auditable flow. The first audience is DeFi users who need research before making a decision. The primary demo compares three research/yield agents, pays one through Binance x402/B402, runs a task, and returns a result with execution proof.

The product has a hard research-only boundary: agents cannot hold user funds, request approvals, sign for users, or execute swaps. Users remain responsible for signing financial actions. PancakeSwap is the first read-only data use case. BSC Testnet remains the target network until security and refund handling are proven.

Core requirements:

- Index ERC-8004 identity, metadata, endpoints, and history on BSC.
- Search/filter by category, active status, price, reputation, and capability.
- Compare up to three agents using raw metrics and explained derived scores.
- Connect MetaMask and Binance Web3 Wallet on BSC Testnet.
- Use Binance B402 V2 for quotes, payment verification, and settlement before execution.
- Manage task states: `created → payment_pending → paid → running → completed/failed/refunded/manual_resolution`.
- Show output, processing time, cost, transaction hash, artifacts, and audit events.
- Build reputation from task success, recency, latency, volume, uptime, and feedback.
- Integrate PancakeSwap read-only liquidity, volume, pool, and yield research.
- Handle offline agents, metadata claims, timeouts, duplicate callbacks, price expiry, delayed transactions, unsafe task requests, RPC failure, indexing checkpoints, and manual payment resolution.

Definition of done originally requested:

- At least 20 indexed agents across four categories.
- Three agents can be compared.
- At least one testnet agent can be paid and run end-to-end.
- Failure states are reproducible without duplicate payment.
- Demo includes transaction hash, audit trail, result, and manual-process benchmark.

## Personas

### DeFi researcher
Wants to compare research quality, cost, latency, and risk evidence before allocating funds.

### Cautious liquidity provider
Needs PancakeSwap pool comparisons without granting approvals or allowing autonomous execution.

### Marketplace operator
Monitors onchain identity, endpoint health, task state, payment reconciliation, and audit evidence.

## Architecture decisions

- **Frontend:** React 19 + TypeScript, React Router, wagmi v2, viem, MetaMask injected connector, official Binance Web3 Wallet connector, shadcn/ui primitives.
- **Backend:** FastAPI with typed Pydantic response models and strict `/api` routes.
- **Database:** MongoDB collections for agents, tasks, audit events, payments, and feedback; UUID public identifiers; Mongo `_id` excluded from API responses.
- **Blockchain:** BSC Testnet chain ID 97. Public BSC testnet RPC and public ERC-8004 Identity Registry are environment-configured defaults; readiness checks verify chain and contract bytecode.
- **Payments:** Strict Binance B402 V2 adapter boundary. Payment stays disabled unless partner base URL, client ID, access token, and RSA key are configured. Browser payment claims are never accepted as proof.
- **Storage:** S3-compatible private object-storage adapter with MongoDB JSON fallback while credentials are absent.
- **Safety:** Research schema rejects private keys, seed phrases, approvals, swaps, and delegated signing requests. Offline agents cannot be hired.
- **Provenance:** Onchain claims and measured metrics are presented separately. Seed profiles never claim live endpoint verification.

## Implemented

### 2026-08-15 — Marketplace foundation

- Added 20 seed agent profiles in four categories, with 18 active and two offline examples.
- Added backend search, category/status/price filters, sorting, detail lookup, and ordered 2–3 agent comparison.
- Added explained reputation metrics: success, uptime, latency, volume, recency, feedback, and composite proof score.
- Built professional search-first marketplace UI with responsive agent cards, filters, clear status, cost, capability, and evidence signals.
- Built persistent comparison selection and detailed side-by-side comparison table.

### 2026-08-15 — Identity, wallet, and safety

- Added MetaMask via wagmi and official Binance Web3 Wallet connector for BSC Testnet.
- Added registry readiness endpoint that verifies chain ID 97 and deployed registry bytecode.
- Added agent identity view with network, registry reference, agent ID, metadata state, and endpoint state.
- Added transaction preview showing network, maximum cost, recipient source, permissions, and payment lock.
- Added server-side rejection for private-key, seed-phrase, token-approval, swap-execution, and delegated-signature requests.

### 2026-08-15 — Task and audit foundation

- Added task draft creation with deterministic `created` state and immutable public UUID.
- Added task detail route, execution timeline, research brief, safety state, and audit trail.
- Added quote expiry design and valid EVM payer validation.
- Added safe 503 payment lock when Binance B402 is unconfigured; no signature or agent call is attempted.
- Added feedback endpoint restricted to completed tasks.
- Added object-storage adapter and explicit MongoDB fallback mode.

### 2026-08-15 — Verification

- Production frontend build succeeds; remaining build output is third-party wallet dependency source-map warnings.
- Backend regression suite passes 13/13 cases.
- Browser checks pass marketplace load, search, compare, agent detail, task draft, audit trail, offline status, and controlled error states.
- Responsive marketplace test shows no horizontal overflow.
- BSC testnet RPC and ERC-8004 registry bytecode checks pass.

### 2026-08-15 — 8004scan BSC Mainnet integration

- Added backend-only authenticated 8004scan client using `X-API-Key`; the key is excluded from frontend bundles, API responses, DOM, console, and application logs.
- Added bounded timeout/retry handling, rate-limit observation, strict `chainId=56` and `isTestnet=false` validation, and last-known-good retention during provider failures.
- Synchronized a ranked sample of 100 real BSC Mainnet ERC-8004 agents from 256,506 available records into a dedicated MongoDB collection with unique `(chain_id, token_id)` upserts.
- Preserved complete upstream payloads privately while exposing only a typed public projection and explicit 8004scan provenance labels.
- Added a separate Onchain explorer with live search, protocol and x402-claim filters, source score/rank/feedback observations, and BscScan links.
- Kept BSC Mainnet identity discovery separate from BSC Testnet payment execution to avoid implying production settlement readiness.
- Removed untrusted remote image loading; deterministic local initials prevent mixed-content, localhost, and blocked-origin failures.
- Extended the same source-preserving sync to BSC Testnet and added network switching in the Onchain explorer.
- Added separate private raw storage and public typed projections for 8004scan feedback history on both BSC networks.
- Replaced text initials with deterministic local identicon artwork across marketplace cards, comparisons, detail views, and both Onchain networks.
- Restored original 8004scan agent icons through a backend-only HTTPS proxy with DNS/private-IP SSRF checks, MIME/size limits, MongoDB caching, and identicon fallback.
- Validated the icon proxy, source/fallback rendering, cache behavior, network isolation, and SSRF defenses with a total backend regression count of 47 passing tests.

### 2026-08-15 — My Agents and complete agent detail

- Added wallet-owned agent lookup through the authenticated 8004scan account endpoint for BSC Mainnet and Testnet, with cached fallback.
- Added complete onchain agent detail routes and UI for owner, registry, services, endpoints, x402, health, source scores, rank, feedback, validations, and provenance.
- Added direct ERC-8004 registration and owner-gated `setAgentURI` metadata editing with chain switching, contract simulation, explicit transaction preview, and wallet-signed writes.
- Metadata is encoded as a self-contained registration `data:` URI, avoiding unavailable object storage; Mainnet requires an additional explicit risk confirmation.
- Added verified 8004scan create/manage deep links and preserved read-only access for disconnected or non-owner visitors.
- Made Binance Wallet connector lazy: it initializes only when the extension is present, preventing background websocket errors for other visitors.

## Current integration status

- **Binance B402 V2:** Not active. Partner credentials and merchant-specific signing schema are not available.
- **Live agent execution:** Not active. Three allow-listed agent endpoints and authentication are not available.
- **Object storage:** Not active. S3-compatible endpoint/bucket credentials are not available; MongoDB fallback is configured.
- **WalletConnect mobile:** Deferred until a WalletConnect Project ID is provided. MetaMask and Binance Wallet connectors are active.
- **PancakeSwap:** Read-only reference snapshot is available and explicitly labeled; live adapter remains pending.
- **ERC-8004 catalog:** Seed profiles are available; full onchain metadata/history indexer remains pending.
- **8004scan:** Active for a 100-agent BSC Mainnet sample. The provider currently reports a 10 requests/minute limit; full 256k-record ingestion is intentionally deferred.

## Prioritized backlog

### P0 — Required for original end-to-end demo

1. Add Binance B402 V2 partner values and merchant RSA signing contract.
2. Implement exact `/supported`, `/verify`, and `/settle` requests from the enabled merchant schema.
3. Add atomic payment state transitions, unique transaction-hash handling, callback inbox, delayed settlement polling, and manual resolution.
4. Configure three agent endpoints; implement allow-listed adapters, timeout, bounded retry, idempotency, and circuit breaker.
5. Configure private object storage and signed artifact downloads.
6. Implement a worker process that resumes safely after crashes and never invokes an agent before verified settlement.
7. Complete one real BSC Testnet payment/run/result flow with transaction hash and execution proof.

### P1 — Data and indexing completeness

1. Build ERC-8004 block indexer with checkpoint, backoff, reorg reconciliation, and metadata fetch validation.
2. Replace seeded identity data with indexed onchain registration/history while preserving provenance labels.
3. Add live PancakeSwap read-only pool adapter and data timestamps.
4. Build the three-agent manual-vs-agent benchmark rubric for quality and latency.
5. Add task list/operator reconciliation views and deterministic timeout/failure scenarios.
6. Add WalletConnect mobile after Project ID configuration.

### P2 — Post-MVP

1. Mainnet readiness and formal security review.
2. Escrow/dispute resolution and supported refund operations.
3. Self-service agent onboarding and endpoint-domain verification.
4. Altana session wallets with spend caps.
5. User-approved swap execution with explicit per-action signatures.
6. Personalized recommendations and richer reputation anomaly detection.

## Next tasks

1. Obtain Binance B402 partner onboarding values and exact V2 merchant schema.
2. Obtain three ERC-8004 agent endpoints and authentication requirements.
3. Obtain S3-compatible object-storage configuration.
4. Implement and test real payment verification, settlement, agent run, artifact storage, and audit proof.
5. Replace PancakeSwap reference data with a timestamped live read-only source.