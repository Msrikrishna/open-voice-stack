# open-voice-stack

Self-hostable voice agent stack. Zero accounts to run.

LiveKit OSS + Ollama (LLM) + faster-whisper (STT) + Kokoro (TTS) +
Silero VAD, glued by `livekit-agents`, configured from a local web UI.

## Quick start

_Coming in Phase 1 — `python launch.py`._

## Architecture

```
Browser ⇄ LiveKit OSS ⇄ agent worker
                          ├─ STT  → faster-whisper-server  (OpenAI-compatible)
                          ├─ LLM  → Ollama                  (OpenAI-compatible)
                          ├─ TTS  → Kokoro-FastAPI          (OpenAI-compatible)
                          └─ VAD  → Silero
```

Everything runs locally. Every base URL is configurable, so you can
swap any component for a hosted backend (OpenAI, Groq, ElevenLabs,
etc.) without changing code.
