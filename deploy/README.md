# Running AgentDock as a service

Two user services, so the public site survives a logout, a crash, or a reboot
without anyone being at the keyboard. They are user units on purpose: this host
has no passwordless sudo, and `loginctl enable-linger` already makes user units
start at boot.

```bash
cp deploy/agentdock-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agentdock-api agentdock-web
```

| Unit | Serves | Port |
|---|---|---|
| `agentdock-api` | FastAPI via uvicorn | 127.0.0.1:8000 → `api.mdloglabs.org` |
| `agentdock-web` | `frontend/build` via `scripts/serve_frontend.py` | 127.0.0.1:3100 → `agents.mdloglabs.org` |

Both bind to loopback only; the Cloudflare tunnel is the sole public path.

## After changing the frontend

```bash
cd frontend && npm run build          # REACT_APP_BACKEND_URL is baked in here
systemctl --user restart agentdock-web
```

The build must be rebuilt for changes to appear — the dev server is no longer
what the public sees. Filenames are content-hashed, so a new build invalidates
Cloudflare's cache by itself; `index.html` is served `no-cache` so it always
names the current bundle.

## Checks

```bash
systemctl --user status agentdock-api agentdock-web
journalctl --user -u agentdock-api -f
```

MongoDB runs in Docker with `restart=unless-stopped`. The API can still win the
boot race against it, so its unit restarts on failure rather than giving up.
