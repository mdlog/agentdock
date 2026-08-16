# Build the Era Hackathon — Registration answers

Draft for <https://docs.google.com/forms/d/e/1FAIpQLSdFb30r24sZcFJVDbMqXNJ1_45BJHanc7eFqwUniScDYZfX9A/viewform>

Copy each block into the matching field. Fields marked **[ANDA]** only you can answer —
I have left them blank rather than inventing something.

Numbers below were measured on the running deployment on 2026-08-16 and are quoted in the
answers. If you submit on a later date, re-check them (`/api/marketplace/pulse`) so the form
does not carry a figure that has moved.

---

## 1. Email
**[ANDA]** — Google records this automatically.

## 2. Full Name
**[ANDA]**

## 3. Email Address
**[ANDA]** — the form asks a second time; use the same address.

## 4. Telegram Handle
**[ANDA]**

## 5. X (Twitter) Handle
**[ANDA]**

## 6. Discord Handle (Optional)
**[ANDA]** — may be left empty.

## 7. How did you hear about this hackathon?
**[ANDA]** — one of: X (Twitter) / Discord / Telegram / BNB Chain Website / Partner Announcement / Friend-Colleague / Other.

## 8. Country and Timezone
**[ANDA]** — e.g. `Indonesia — WIB (UTC+7)`

## 9. Solo builder or a team?
**[ANDA]** — Solo or Team.

## 10. Number of Teammates
**[ANDA]** — `1 (Solo)` if you are building alone.

## 11. Teammate Names, Emails, and Roles
**[ANDA]** — required even when solo. If solo, something like:

```
Solo builder. <Full name> — <email> — full stack: Solidity/ERC-8004 integration,
FastAPI backend, React frontend, deployment and operations.
```

---

## 12. Project Name

```
AgentDock
```

## 13. One-Line Pitch

Primary:

```
AgentDock calls every ERC-8004 agent on BNB Chain before listing it, so you hire the 55 that answer instead of guessing among 257,115.
```

Shorter alternative, if the field is tight:

```
The BNB Chain agent marketplace that tests every agent before listing it.
```

## 14. Project Description

```
AgentDock is an agent marketplace for BNB Chain built on the ERC-8004 identity registry
(0x8004A169FB4a3325136EB29fA0ceB6D2e539a432). It answers the question the registry cannot:
of the agents registered on chain, which ones actually work?

Registration proves only that somebody wrote a URL into metadata. AgentDock has indexed all
257,115 agents on BSC mainnet, called 16,264 of their published endpoints over MCP and A2A,
and found 55 that answer. Every listing carries the result of that call — what we requested,
the URL we actually reached after filling in id templates and following agent cards, what came
back, and when. An agent whose host reports it as unbound says so on its page, even where the
indexer shows a green "Active" badge. Nothing on the site claims an agent works because it was
registered.

Hiring is a few clicks and needs no Agent Studio knowledge: pick an agent, choose one of the
objectives read from its own live tool list, and run it. Free agents run directly; paid ones
settle through Binance b402 / x402 v2 with EIP-3009 transferWithAuthorization against an
on-chain-verified asset allowlist, alongside 34 payable resources synced from the b402 Bazaar.
Categories come from the tools an agent actually exposes rather than from its name, and the
catalogue keeps itself current with a head sync every 10 minutes and a re-verification sweep
every hour, because a verdict that is never rechecked becomes a claim.

Stack: FastAPI + MongoDB, React 19 + TypeScript, wagmi/viem, MetaMask and Binance Wallet.
Live at https://agents.mdloglabs.org, API at https://api.mdloglabs.org, 123 backend tests
passing. Safety boundaries are enforced server-side: no swaps, approvals, or transfers are
executed on a user's behalf.
```

> Trim from the end if the field has a character limit — the first two paragraphs carry the argument.

## 15. Sub-prize tracks you are interested in

Recommendation: **TermiX**.

- **TermiX** — we already read Termix-hosted agents in production. Agent #255133 (Grid-v3.agent)
  resolves through `platform-backend.prod.termix.live`, and its platform's own `UNBOUND` status is
  what our verdict quotes. That is a real, demonstrable link today.
- **PancakeSwap** — only tick this if you intend to build the integration. The earlier
  PancakeSwap snapshot was mock data and I removed it; there is no live tie right now. The live
  Rebalancing (76 agents) and Yield Optimisation (616) categories would make it a natural
  addition, but it is not built.
- **AltLayer** — no current connection. I would not tick it.

## 16. Project GitHub Repo Link

```
https://github.com/mdlog/agentdock
```

Verified reachable (HTTP 200) and public.

## 17. Prototype Stage

```
Working MVP
```

Deployed, publicly reachable, real on-chain and third-party data, 123 backend tests passing.

## 18. BSC/EVM Experience Level
**[ANDA]** — your own call. Given what is in this repo (a live ERC-8004 integration, EIP-3009
payment signing, contract reads via viem), `Intermediate` or `Advanced` both read as honest.

## 19. Check all areas you are comfortable with
**[ANDA]** — what the project itself demonstrates: **AI agent frameworks** (MCP and A2A clients
written from the transport up), **Onchain data/APIs** (ERC-8004 registry reads, 8004scan
indexer, BscScan), **Frontend development** (React 19 + TypeScript). Solidity appears only as
contract reads and metadata writes, not as contracts we authored — tick it only if it is true
of you generally.

## 20. Interested in mentorship?
**[ANDA]** — Yes / No.

## 21. Availability for build (Aug 5 – Sep 9) and judging (Sep 9 – Sep 23)

```
Yes, I confirm availability
```

## 22. Wallet address in case you win
**[ANDA]** — a BEP-20 address you control. I have deliberately not filled this in, and you
should paste it yourself rather than have it pass through anything else.

## 23. Additional Notes (Optional)

Optional, but this is a good place to state what is real and what is not — it tends to help
rather than hurt:

```
Everything on the site runs against live data: the ERC-8004 registry on BSC mainnet, the
8004scan indexer, and each agent's own endpoint. There is no seeded catalogue — 20 placeholder
agents were removed rather than dressed up.

Two things are honestly incomplete. Binance b402 settlement is implemented end to end and
covered by tests, but has not yet moved real funds because partner credentials are still
pending; the 34 b402 Bazaar resources are synced and priced from the live catalogue. And of the
345 Grid Trading agents registered on chain, zero are callable — 329 publish no endpoint and 16
are unbound. We show that number rather than hiding the category.
```

## 24. Terms of Participation
**[ANDA]** — read the terms and tick it yourself. I am not agreeing to terms on your behalf.

---

## Figures quoted above (measured 2026-08-16)

| figure | value | source |
|---|---|---|
| agents indexed, BSC mainnet | 257,115 | `/api/marketplace/pulse` |
| endpoints called | 16,264 | same |
| agents that answered | 55 | same |
| registered today | 343 | same |
| b402 Bazaar resources | 34 | `/api/b402/resources` |
| backend tests passing | 123 | `pytest tests/ -q` |
| latest commit | `7f1f09e` | `git log` |
