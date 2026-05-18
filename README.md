<h1 align="center">open-voice-stack</h1>

<p align="center">
  <b>Run a real-time voice agent end-to-end on your laptop.</b><br>
  Clone the repo, run three commands, talk to it in your browser. No
  cloud accounts, no API keys, no credit card.
</p>

<p align="center">
  <code>LiveKit OSS</code> · <code>Ollama</code> · <code>faster-whisper</code> ·
  <code>Kokoro</code> · <code>Silero VAD</code> · <code>Phoenix</code>
</p>

---

**Why it exists.** Most voice-agent starters wire you into 3-4 paid
SaaS providers before the first "hello world". This repo replaces every
hosted dependency with an OpenAI-compatible local server, so you can
build, demo, and iterate on a voice agent without an internet
connection — and swap any component back to a hosted one with a single
`base_url` change in the UI.

## Quick start

Setup, run, and verification all live in [AGENTS.md](AGENTS.md).

TL;DR: install Colima + Ollama + Python 3.12, then in three terminals:

```bash
docker compose up -d
python -m agent.worker dev
python -m dev_ui.server
```

Open <http://127.0.0.1:8080>.

## Architecture

```
Browser ⇄ LiveKit OSS ⇄ agent worker
                          ├─ STT  → faster-whisper-server  (OpenAI-compatible)
                          ├─ LLM  → Ollama                  (OpenAI-compatible)
                          ├─ TTS  → Kokoro-FastAPI          (OpenAI-compatible)
                          └─ VAD  → Silero
```

Every base URL is configurable in the UI, so any component can be
swapped for a hosted backend (OpenAI, Groq, ElevenLabs, etc.) without
changing code.

## Extending the agent

The agent is a thin wrapper around `livekit-agents`'s `AgentSession`,
which supports the standard extensibility hooks:

- **Tools** — Decorate Python functions with `@function_tool` and pass
  them to `Agent(tools=[...])` in `agent/worker.py`. The LLM can then
  call them mid-conversation. See the
  [livekit-agents tool calling docs](https://docs.livekit.io/agents/build/tools/).
- **Knowledge** — Inject any text into `Agent(instructions=...)` or
  prepend `ChatContext` entries at session start (RAG pattern). For
  hot-reload, swap reads for a `watchfiles.awatch` loop over your
  source directory.

Both extensions only touch `agent/worker.py` — no plumbing changes.

## Default ports

| Service                 | URL                          |
|-------------------------|------------------------------|
| LiveKit signaling       | `ws://localhost:7880`        |
| faster-whisper-server   | `http://localhost:8000/v1`   |
| Ollama (host process)   | `http://localhost:11434/v1`  |
| Kokoro-FastAPI          | `http://localhost:8880/v1`   |
| Dev UI                  | `http://localhost:8080`      |
