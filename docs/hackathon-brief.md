# Build the Era — event brief (as shared by organiser, saved 2026-08-16)

Verbatim copy of the track details the organiser published, kept here so every
improvement decision can be traced to a judged criterion.

## Main Track: Build the BNB Agent Studio Marketplace

Build the best agent marketplace for BNB Chain.

Somewhere, users need to find agents, understand what they do, and hire them in
a few clicks. Right now that place doesn't exist. So: build it.

The top submission gets officially adopted as the BNB Agent Studio marketplace,
the canonical front door for every agent on BSC. This isn't a demo day.
Whatever you ship here is what real users interact with next.

### What you're building

A front end that surfaces agent data, lets users discover and activate agents
by category, and doesn't make them think too hard about it.

Four categories, all first-class:

| Category | What the agent does |
|---|---|
| Rebalancing | Manages LP ranges, resets positions automatically |
| Grid Trading | Places and manages automated grid orders |
| Yield Optimisation | Routes liquidity to the highest available APR |
| Health Factor Monitoring | Protects lending positions from liquidation |

Single-category submissions score poorly. All four, equally deep, is the bar.

### How you're judged

Three judges, scored independently, then compared.

- **Functionality** — the full journey works end to end: land, find an agent by
  category, understand what it does, activate it, with minimal friction.
  Someone with zero Agent Studio knowledge should be able to get through it
  without hitting a dead end.
- **Data Quality** — real-time, accurate data that goes beyond basic counts. A
  user should be able to look at what you're showing and make a genuinely
  informed call on which agent to hire.
- **Agent Diversity** — all four categories surfaced with equal depth. A
  submission that treats one category as the main event and the rest as an
  afterthought won't score well here.

More criteria assessed in the second phase ("stay tuned").

### Timeline

Build: NOW! → Shortlist: submissions close, top 3 shortlisted publicly →
Phase 2: [REDACTED] → Winner announced.

### Tooling

Describe it, and Cursor scaffolds it against the BNB Agent Studio CLI. Agent
Studio runs on AWS underneath.

### Eligibility

- Open globally, individuals or teams. One entry per team.
- Submission must be functional and publicly accessible during judging.
- **Agents surfaced on your marketplace must be live on BSC.**

## Partner Track: Best Built with Altana

Altana is self-custodial infrastructure for sovereign agents. An agent holds
its own wallet and its own key: no custodian, no shared treasury, no human
signing every transaction. The owner grants a scoped session (which calls the
agent may make, how much it may spend, when the permission expires); grant and
revoke stay with the owner. Every session key is registered in a public onchain
registry (Keystore), so any app or agent can check which keys hold authority on
a wallet and when that authority expires. Revocation is one transaction and
takes effect immediately.

The track: build an agent marketplace on BNB Chain where the agents transact
for themselves, inside limits their users set.

To be considered, the submission must show live onchain transactions in the
Altana explorer (testnet counts, mainnet stronger):

- Agents on their own Altana wallets.
- Sessions with real limits: call allowlist, spend cap, expiry.
- Sessions registered in Keystore (integration read onchain, not from pitch).
- Real onchain transactions through a session key.
- User-facing control: a user can see what their agent may do, and revoke it,
  inside the product.

Bonus: hire BNB Agent Studio agents through ERC-8183 using the Altana ERC-8183
SDK (buyer and seller side both shipped); implement sell over x402/B402 using
the x402 server SDK (`@altananetwork/x402-server`, `hireErc8183Agent`).

## Partner Track: TermiX Challenge

One line: does hiring an agent on this marketplace actually beat doing the job
yourself, and can you prove it with numbers? No TermiX integration asked; the
submission is the marketplace itself. **TermiX will hire from the marketplace
themselves and evaluate what comes back.**

| Criterion | Weight | "Great" looks like |
|---|---|---|
| Value of the services | 30% | Real working agents at a price and speed that beat the alternative |
| Proven agent advantage | 30% | Measured, not asserted — backed by the required Agent Advantage Report |
| High-stakes categories & track record | 20% | Trading, stock/equities, security agents weighted above general-purpose. Trading agents need a real record: win rate, the window, the risk taken |
| Marketplace quality | 20% | Find, compare, hire, without instructions |

### Required: Agent Advantage Report

- At least 3 real tasks run both ways: with an agent hired through the
  marketplace vs without.
- For each task: time, cost, output quality, with actual outputs attached.
- At least one task from trading, stock or security.
- "Proven agent advantage" (30%) is scored against this report.

## Partner Challenge: PancakeSwap

The agent must deliver a real benefit to PancakeSwap traders or liquidity
providers. Examples: smarter liquidity management, finding better yields,
researching market movements to find demand where creating PancakeSwap pools
could improve liquidity efficiency, or executing safe automated swaps using
PancakeSwap products without ever putting user funds at risk.
