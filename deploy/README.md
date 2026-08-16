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
./scripts/build_frontend.sh          # REACT_APP_BACKEND_URL is baked in here
#                                     builds to a staging dir and swaps only on
#                                     success, so a broken build cannot 502 the site
systemctl --user restart agentdock-web
```

The build must be rebuilt for changes to appear — the dev server is no longer
what the public sees. Filenames are content-hashed, so a new build invalidates
Cloudflare's cache by itself; `index.html` is served `no-cache` so it always
names the current bundle.

## Backups

`agentdock-backup.timer` snapshots MongoDB daily, keeping the last seven.
Re-syncing the 256k catalogue costs about an hour of a sponsor's rate limit;
the tasks and audit trail cannot be re-derived at all.

```bash
cp deploy/agentdock-backup.* ~/.config/systemd/user/
systemctl --user enable --now agentdock-backup.timer
./scripts/backup_mongo.sh                              # or run one now
```

Restore: `docker exec -i agentdock-mongo mongorestore --archive --gzip --drop < <snapshot>`

## Checks

```bash
systemctl --user status agentdock-api agentdock-web
journalctl --user -u agentdock-api -f
```

MongoDB runs in Docker with `restart=unless-stopped`. The API can still win the
boot race against it, so its unit restarts on failure rather than giving up.
