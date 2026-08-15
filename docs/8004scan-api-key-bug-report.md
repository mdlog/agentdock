# [Bug]: API key ignored via the documented `X-API-Key` header; tier only applied via undocumented `Authorization: Bearer` on the non-public surface

### Affected Component

API (Backend) + Documentation (OpenAPI spec / Builder Hub)

### Severity

High — a valid, paid key gets anonymous rate limits when used exactly as documented. Every developer who follows the docs is silently throttled.

---

### Summary

A valid API key bound to a high-throughput tier is **not honored when sent as `X-API-Key`** — the header that the OpenAPI spec, the Builder Hub, and the in-app "API Usage Guide" all instruct you to use. The tier is applied **only** when the key is sent as `Authorization: Bearer <key>`, and **only** against the **non-public** `/api/v1/*` base URL — a transport and a base URL that appear **nowhere** in the public documentation.

There are two distinct, independently reproducible defects:

1. **Documented path is dead.** On `/api/v1/public/*` (the only server in the OpenAPI spec), a valid key sent as `X-API-Key` never rises above the anonymous `10 req/min` limit.
2. **Working path is undocumented.** On `/api/v1/*` (absent from the spec), the key must be sent as `Authorization: Bearer`; `X-API-Key` is ignored there.

A bogus key sent as `Authorization: Bearer` falls back to anonymous limits, which proves the server **does** validate the key value and resolve a tier — just through the one transport its own documentation never mentions.

---

### What the documentation says

- **OpenAPI spec** (`GET https://8004scan.io/api/v1/public/docs/openapi.json`, v1.0.0):
  - `servers`: exactly one entry — `https://8004scan.io/api/v1/public`
  - `components.securitySchemes`: exactly one scheme — `{"type":"apiKey","in":"header","name":"X-API-Key"}`
  - `info.description`: *"All endpoints support optional API key authentication via the `X-API-Key` header."*
  - Tier table: `anonymous 10/100 · free_api 30/1,000 · basic 100/10,000 · pro 500/100,000 · enterprise 2000/unlimited`
  - The scheme description links to `https://8004scan.io/developers/api-keys` **for key issuance — that URL returns HTTP 404.**
- **In-app "API Usage Guide"** (profile → API Keys): every example uses `curl -H "X-API-Key: YOUR_API_KEY"`.
- **No public documentation mentions** `Authorization: Bearer`, the `/api/v1/*` (non-public) base URL, or the `3000/3,000,000` allocation observed below.

---

### Measured behavior

All requests: HTTP/2 200, `User-Agent: AgentDock/1.0`, key sent **only** in headers (never in a URL), calls spaced ≥1.5s, 2026-08-15 UTC. Key value redacted as `<KEY>`.

| Base URL | Auth transport | `limit/min` | `limit/day` |
|---|---|---|---|
| `/api/v1/agents` (non-public) | *(none)* | 180 | 20,000 |
| `/api/v1/agents` | **`Authorization: Bearer <KEY>`** | **3,000** | **3,000,000** |
| `/api/v1/agents` | `Authorization: Bearer <bogus>` | 180 | 20,000 |
| `/api/v1/agents` | `X-API-Key: <KEY>` | 180 | 20,000 |
| `/api/v1/public/agents` | *(none)* | 10 | 100 |
| `/api/v1/public/agents` | `Authorization: Bearer <KEY>` | 10 | 100 |
| `/api/v1/public/agents` | `X-API-Key: <KEY>` | 10 | 100 |

**Key observations**

- The `Bearer <KEY>` elevation on `/api/v1/agents` reproduced across three requests, decrementing its own private bucket: `remaining-minute` 2998 → 2997 (H2 14:19:55, H3 14:19:58 UTC), independently confirmed at 14:19:09.
- The `Bearer <bogus>` control stayed at `180/20,000` (H4 14:20:00 UTC) — this is the decisive control: the server **validates the real key** and maps it to a tier.
- `X-API-Key: <KEY>` on the same non-public surface stayed at `180/20,000` (H5 14:20:02) — the documented header is ignored here.
- On `/api/v1/public/*`, **no** transport elevated above anonymous `10/min`, real key and bogus key alike (H6–H8 14:20:05–09; also request-ids `u3eOAmOQEMOs-FLcdVHpl` and `eFpBEy9kKMIgfUyQpQdmp` at 14:10:44 / 14:10:47).
- Sending `X-API-Key` on `/api/v1/public/agents` **does** create a per-key-string rate bucket separate from the per-IP anonymous bucket — but always at the anonymous `10/min` limit, so it buckets without validating.
- Non-public `/api/v1/*` responses carry **no** `x-request-id` header (so those rows are cited by UTC timestamp).

---

### Steps to reproduce

```bash
KEY="<your active 8004scan API key>"
UA="8004scan-bug-report/1.0"

# 1. Documented path — key sent as documented. Expect a Pro limit; get anonymous 10.
curl -s -D - -o /dev/null -H "User-Agent: $UA" -H "X-API-Key: $KEY" \
  "https://8004scan.io/api/v1/public/agents?page=1&limit=1&chainId=56" | grep -i ratelimit
# -> x-ratelimit-limit: 10

# 2. Non-public path, documented header. Still ignored.
curl -s -D - -o /dev/null -H "User-Agent: $UA" -H "X-API-Key: $KEY" \
  "https://8004scan.io/api/v1/agents?chain_id=56&limit=1" | grep -i ratelimit
# -> x-ratelimit-limit-minute: 180 ; x-ratelimit-limit-day: 20000

# 3. Non-public path, UNDOCUMENTED Bearer header. Tier applied.
curl -s -D - -o /dev/null -H "User-Agent: $UA" -H "Authorization: Bearer $KEY" \
  "https://8004scan.io/api/v1/agents?chain_id=56&limit=1" | grep -i ratelimit
# -> x-ratelimit-limit-minute: 3000 ; x-ratelimit-limit-day: 3000000

# 4. Control: bogus Bearer value stays anonymous, proving (3) is real key validation.
curl -s -D - -o /dev/null -H "User-Agent: $UA" -H "Authorization: Bearer bogus-000" \
  "https://8004scan.io/api/v1/agents?chain_id=56&limit=1" | grep -i ratelimit
# -> x-ratelimit-limit-minute: 180 ; x-ratelimit-limit-day: 20000
```

> Note: 8004scan's Cloudflare returns HTTP 403 (error 1010) to requests with a default client User-Agent (e.g. `python-httpx`, `python-urllib`). Set an explicit `User-Agent` or these commands fail for an unrelated reason.

---

### Expected behavior

Either of the following would resolve it:

- **(preferred)** Honor `X-API-Key` tier elevation on `/api/v1/public/*` exactly as the spec and Builder Hub promise, so a valid key exceeds `10 req/min` there; **or**
- Update the OpenAPI spec and the in-app Usage Guide to document `Authorization: Bearer`, add the `/api/v1/*` base URL to `servers`, publish the `3000/3,000,000` tier, and fix the dead `/developers/api-keys` link.

---

### Secondary issue (unrelated to auth)

`GET https://8004scan.io/api/v1/public/agents/search` returned **HTTP 502 `BACKEND_ERROR`** for both anonymous and authenticated callers across every attempt (14:14 and 14:17 UTC, multiple `limit` values). Appears to be a live outage of the search endpoint.

---

### Environment

- Date of measurements: 2026-08-15 (UTC timestamps inline above)
- Server: Vercel (per `server:` and `x-vercel-*` response headers)
- Account tier: complimentary Pro (Build the Era Hackathon), valid through 2026-09-09
- Observed allocation via Bearer: `3000 req/min`, `3,000,000 req/day` — matches no published tier row
