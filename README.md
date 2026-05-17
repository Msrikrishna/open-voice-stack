# open-voice-stack

Self-hostable voice agent stack. Zero accounts to run.

LiveKit OSS + Ollama (LLM) + faster-whisper (STT) + Kokoro (TTS) +
Silero VAD, glued by `livekit-agents`, configured from a local web UI.

## Phase 1 — manual vertical slice

One-command bootstrap (`launch.py`) is Phase 2. For now, three terminals.

### Prerequisites (macOS, one-time setup)

We use [Colima](https://github.com/abiosoft/colima) as the container
runtime — open source, free, and works well on Apple Silicon. The
`docker` CLI talks to Colima's daemon.

```bash
# 1. Container runtime + CLI.
brew install docker colima

# 2. Start the VM (4 vCPU / 8 GB is enough for whisper + kokoro + livekit).
colima start --cpu 4 --memory 8

# 3. Point the docker CLI at Colima's daemon.
docker context use colima

# 4. LLM runtime — install Ollama and pull a model.
#    Any model in `ollama list` works; gemma4:e4b is a good small default.
brew install ollama
ollama serve &              # in a background terminal, or use the .app
ollama pull gemma4:e4b
```

Also needed: Python 3.12 (`brew install python@3.12`). 3.14 may lack
wheels for some C-extension deps (silero, onnxruntime).

### Run the stack

```bash
cp .env.example .env

# 1. Local services (LiveKit, Whisper, Kokoro).
docker compose up

# 2. Python deps (in a venv).
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
