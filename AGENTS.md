# AGENTS.md — running open-voice-stack

Spec for humans (and coding agents) to bring this repo up on a fresh
Mac and verify every component end-to-end. No bootstrap script — every
step below is a shell command you (or your agent) run directly.

---

## 1. Prerequisites (one-time, macOS)

```bash
# Container runtime + CLI (Colima is the open-source Docker daemon).
brew install docker colima

# Start the VM. 4 vCPU / 8 GB fits whisper + kokoro + livekit comfortably.
colima start --cpu 4 --memory 8

# Point the docker CLI at Colima's daemon (only needed if you dont have
# Docker Desktop installed; harmless either way).
docker context use colima

# LLM runtime + a small model that fits on most laptops.
brew install ollama
ollama serve &                  # background; or start the Ollama.app
ollama pull gemma4:e4b          # or any model in `ollama list`

# Python — 3.12 is the safe choice. 3.14 may lack wheels for some
# C-extension deps (silero, onnxruntime).
brew install python@3.12
```

Verify before continuing:

```bash
docker info > /dev/null      && echo "✓ docker daemon reachable"
colima status                # should print "running"
ollama list                  # at least one model present
python3.12 --version         # 3.12.x
```

---

## 2. First-time project setup (in the repo root)

```bash
# Copy env template once. .env is gitignored; edit freely.
cp .env.example .env

# Python venv + editable install of this project.
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

## 3. Launch (every time)

Four things to start. Use three terminals — containers in the
background, agent + UI in their own terminals so you can see logs.

```bash
# Terminal 1 — local services (LiveKit, faster-whisper-server, Kokoro).
docker compose up -d
docker compose logs -f          # optional: watch container logs

# Terminal 2 — agent worker.
source .venv/bin/activate
python -m agent.worker dev

# Terminal 3 — dev UI (mints tokens, dispatches the agent).
source .venv/bin/activate
python -m dev_ui.server

# Then open the console in your browser.
open http://127.0.0.1:8080
```

Ctrl-C in each Python terminal stops that process. Containers stay
running between launches; bring them down with `docker compose down`.

---

## 4. Verification

### Per-service health (containers)

```bash
docker compose ps                            # all four "running"
curl -s http://localhost:7880               # LiveKit returns "OK"
curl -s http://localhost:8000/v1/models | jq # whisper lists models
curl -s http://localhost:8880/v1/audio/voices | jq  # kokoro voices, af_bella present
curl -s http://localhost:6006/health         # phoenix health → 200
```

### Ollama (host process, not in compose)

```bash
curl -s http://localhost:11434/v1/models | jq '.data[].id'
# Whichever model name you put in .env's LLM_MODEL must appear here.
```

### End-to-end smoke test

1. Open <http://127.0.0.1:8080>. Settings sidebar pre-fills from `.env`.
2. Click **Connect**. Status pill should flip `connecting → connected`
   within ~2 seconds.
3. Say "hello". Within ~3 seconds you should hear a spoken reply and
   see both user + agent transcripts in the chat panel.

If any of those fail, see Troubleshooting below.

### Observability (Phoenix) + Sessions

After a call ends:

1. The agent writes `sessions/<room>/{meta.json, transcript.json}` on
   disk. Click **refresh** in the sidebar's **Sessions** section, then
   click a row to view the transcript inline.
2. The agent also exports OTEL spans to Phoenix on `:4317`. Open
   <http://localhost:6006> directly, or click the **view trace in
   Phoenix ↗** link in the session viewer. The `trace_id` in
   `meta.json` is what to search for in the Phoenix UI.

```bash
# Verify Phoenix is up.
curl -s http://localhost:6006/health
# List the recorded sessions on disk.
ls sessions/
# Inspect a transcript directly.
cat sessions/<room>/transcript.json | jq
```

---

## 5. Configuration

`.env` controls defaults; the dev UI re-reads it on every page load
(no need to restart the server after editing). All seven provider
fields can be overridden per-session in the UI sidebar — the chosen
values are forwarded to the worker via LiveKit room metadata.

| `.env` key       | Effect                                                  |
|------------------|---------------------------------------------------------|
| `LLM_MODEL`      | Default LLM (must exist in `ollama list`).              |
| `LLM_BASE_URL`   | Swap to any OpenAI-compatible chat endpoint.            |
| `STT_MODEL`      | faster-whisper model id (auto-downloads on first use).  |
| `TTS_VOICE`      | Kokoro voice id (`af_bella`, `am_adam`, …).             |
| `LIVEKIT_*`      | Only change if you're pointing at non-default LiveKit.  |

Browser hard-reload (Cmd-Shift-R) after editing `.env` and the
sidebar form will reflect the new values.

---

## 6. Troubleshooting

### `Connect failed: could not establish pc connection`

WebRTC ICE failure. On Mac container runtimes (Colima, Docker Desktop)
UDP can't be reliably routed back from container → host LAN IP.
`livekit.yaml` is already configured to force TCP-only ICE on
`:7881` — but verify:

```bash
docker compose logs livekit | grep "ICE candidate pair" | tail -3
# Expect:  local: 127.0.0.1:7881 tcp type(host/)  state: succeeded
# Bad:     local: ...:7882 udp ...                state: failed
```

If you see UDP failures, the `livekit.yaml` change didn't take effect.
Force-recreate: `docker compose up -d --force-recreate livekit`.

### `model 'xxx' not found` from the LLM endpoint

The model name in the UI doesn't match what Ollama actually has.

```bash
ollama list                 # what's pulled
ollama pull <model>         # to add one
```

Then hard-reload the browser and Connect again.

### Kokoro container exits with `Model files not found!`

First-time download didn't happen. `docker-compose.yml` sets
`DOWNLOAD_MODEL=true`. Recreate to retry:

```bash
docker compose up -d --force-recreate kokoro
docker compose logs -f kokoro
```

Wait for "Application startup complete." (~330 MB download).

### Sessions sidebar is empty after a call

Either the call didn't produce any conversation items (agent never
spoke) or the agent worker can't write to `./sessions/`. Check:

```bash
ls -la sessions/
# Each call should create a dir named like `dev-ui-abc12345/`
# with meta.json + transcript.json inside.
```

If `sessions/` is missing or the agent log mentions a write error,
ensure the working directory at `python -m agent.worker dev` time is
the repo root.

### Phoenix UI loads but shows no traces

The agent exporter targets `http://localhost:4317`. Verify the Phoenix
container exposes 4317 and the agent isn't pointed elsewhere:

```bash
docker compose ps phoenix     # should show 4317 published
echo $OTEL_ENDPOINT           # leave unset to use the default
```

Restart the agent worker after starting Phoenix the first time — the
exporter caches DNS at startup.

### Whisper / Kokoro models gone after `docker compose down -v`

`-v` removes named volumes. Model files live in host-mounted
`./models/whisper/` and `./models/kokoro/`, which `down -v` does
**not** touch. They're only lost if you `rm -rf ./models/`.

### Port already in use

```bash
lsof -i :7880 -i :7881 -i :8000 -i :8080 -i :8880
```

Kill the conflicting process or change the published port in
`docker-compose.yml` (and the matching `*_BASE_URL` in `.env`).

---

## 7. What lives where

```
.
├── AGENTS.md              # this file — full setup + verification spec
├── docker-compose.yml     # LiveKit + whisper + kokoro + phoenix
├── livekit.yaml           # TCP-only ICE config (Colima-safe)
├── .env.example           # copy → .env on first run
├── pyproject.toml         # livekit-agents[openai,silero], aiohttp, dotenv
├── agent/
│   └── worker.py          # AgentSession + OTEL export + session writer
├── dev_ui/
│   ├── server.py          # aiohttp: tokens, dispatch, sessions API
│   └── static/            # one-page console (index.html, app.js, styles.css)
├── sessions/              # per-call meta.json + transcript.json (gitignored)
├── data/                  # Phoenix SQLite store (gitignored)
└── models/                # host-mounted whisper + kokoro weights (gitignored)
```
