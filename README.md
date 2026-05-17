# open-voice-stack

Self-hostable voice agent stack. Zero accounts to run.

LiveKit OSS + Ollama (LLM) + faster-whisper (STT) + Kokoro (TTS) +
Silero VAD, glued by `livekit-agents`, configured from a local web UI.

## Phase 1 — manual vertical slice

One-command bootstrap (`launch.py`) is Phase 2. For now, three terminals:

**Prerequisites:** Docker, Python 3.11+, and [Ollama](https://ollama.com)
running locally with a model pulled (`ollama pull qwen2.5:7b-instruct`).

```bash
cp .env.example .env

# 1. Local services (LiveKit, Whisper, Kokoro).
docker compose up

# 2. Python deps (in a venv — 3.12 recommended, some C-ext deps
#    don't have 3.14 wheels yet).
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Agent worker (in its own terminal).
python -m agent.worker dev

# 4. Dev UI (in its own terminal).
python -m dev_ui.server
```

Open <http://127.0.0.1:8080>, click **Connect**, say "hello".

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

## Default ports

| Service                 | URL                          |
|-------------------------|------------------------------|
| LiveKit signaling       | `ws://localhost:7880`        |
| faster-whisper-server   | `http://localhost:8000/v1`   |
| Ollama (host process)   | `http://localhost:11434/v1`  |
| Kokoro-FastAPI          | `http://localhost:8880/v1`   |
| Dev UI                  | `http://localhost:8080`      |
