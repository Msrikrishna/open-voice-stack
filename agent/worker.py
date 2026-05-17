"""open-voice-stack agent worker.

Everything talks to OpenAI-compatible HTTP endpoints:
    STT  → faster-whisper-server  (default :8001/v1)
    LLM  → Ollama or any chat completions URL (default :11434/v1)
    TTS  → Kokoro-FastAPI           (default :8002/v1)
    VAD  → Silero (in-process)

Per-room overrides are read from `room.metadata` (JSON), so the dev UI can
swap voice / model / system prompt without restarting the worker.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    metrics,
)
from livekit.plugins import openai, silero

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="[agent] %(levelname)s %(message)s")
logger = logging.getLogger("open_voice_stack.agent")

AGENT_NAME = os.environ.get("AGENT_NAME", "open-voice-agent")

DEFAULT_STT_BASE_URL = os.environ.get("STT_BASE_URL", "http://localhost:8000/v1")
DEFAULT_STT_MODEL = os.environ.get("STT_MODEL", "Systran/faster-whisper-base.en")
DEFAULT_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:e4b")
DEFAULT_LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.4"))
DEFAULT_TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "http://localhost:8880/v1")
DEFAULT_TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
DEFAULT_TTS_VOICE = os.environ.get("TTS_VOICE", "af_bella")

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful AI voice assistant.

# AI DISCLOSURE
- In your opening turn, mention you are an AI assistant.
- If asked directly, confirm in one sentence.

# VOICE OUTPUT — STRICT
- ONE short sentence per turn. After the sentence ends, STOP.
- No markdown, lists, code, headings, or emoji.
- Numbers as words: "twelve dollars", not "$12.00".
"""

DEFAULT_GREETING = (
    "Greet the user warmly, identify yourself as an AI assistant in the same "
    "sentence, and ask how you can help today. One sentence, then pause."
)


# TTS reads "(note)" and "[placeholder]" literally. Strip stage directions
# before they reach the synthesizer.
_STAGE_DIRECTION_RE = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*")


async def _strip_stage_directions(text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
    buffer = ""
    async for chunk in text_stream:
        buffer += chunk
        if (
            not ("(" in buffer or "[" in buffer)
            or ("(" in buffer and ")" in buffer)
            or ("[" in buffer and "]" in buffer)
        ):
            cleaned = _STAGE_DIRECTION_RE.sub(" ", buffer)
            if cleaned:
                yield cleaned
            buffer = ""
    if buffer:
        yield _STAGE_DIRECTION_RE.sub(" ", buffer)


def prewarm(job: JobProcess) -> None:
    job.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.6,
        min_speech_duration=0.1,
        activation_threshold=0.5,
    )


def _parse_room_metadata(ctx: JobContext) -> dict[str, Any]:
    room = getattr(ctx, "room", None)
    raw_meta = getattr(room, "metadata", None) or "" if room else ""
    if not raw_meta:
        return {}
    try:
        meta = json.loads(raw_meta)
    except (TypeError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    ctx.log_context_fields = {"room": getattr(ctx.room, "name", "<unknown>")}

    meta = _parse_room_metadata(ctx)

    stt_base_url = meta.get("stt_base_url") or DEFAULT_STT_BASE_URL
    stt_model = meta.get("stt_model") or DEFAULT_STT_MODEL
    llm_base_url = meta.get("llm_base_url") or DEFAULT_LLM_BASE_URL
    llm_model = meta.get("llm_model") or DEFAULT_LLM_MODEL
    llm_temperature = float(meta.get("llm_temperature") or DEFAULT_LLM_TEMPERATURE)
    tts_base_url = meta.get("tts_base_url") or DEFAULT_TTS_BASE_URL
    tts_model = meta.get("tts_model") or DEFAULT_TTS_MODEL
    tts_voice = meta.get("tts_voice") or DEFAULT_TTS_VOICE
    system_prompt = meta.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    greeting = meta.get("greeting") or DEFAULT_GREETING

    logger.info(
        "session config: stt=%s/%s llm=%s/%s tts=%s/%s voice=%s",
        stt_base_url, stt_model,
        llm_base_url, llm_model,
        tts_base_url, tts_model, tts_voice,
    )

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        # The OpenAI-compatible servers don't check the API key, but the
        # openai client refuses to start without one — pass a dummy.
        stt=openai.STT(
            base_url=stt_base_url,
            api_key="not-needed",
            model=stt_model,
            language="en",
        ),
        llm=openai.LLM(
            base_url=llm_base_url,
            api_key="not-needed",
            model=llm_model,
            temperature=llm_temperature,
        ),
        tts=openai.TTS(
            base_url=tts_base_url,
            api_key="not-needed",
            model=tts_model,
            voice=tts_voice,
        ),
        min_endpointing_delay=0.8,
        max_endpointing_delay=4.0,
        min_interruption_duration=0.7,
        min_interruption_words=3,
        false_interruption_timeout=2.0,
        resume_false_interruption=True,
        discard_audio_if_uninterruptible=True,
        preemptive_generation=False,
        max_tool_steps=1,
        tts_text_transforms=[
            "filter_emoji",
            "filter_markdown",
            _strip_stage_directions,
        ],
    )

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def _log_summary(_reason: str) -> None:
        try:
            logger.info("session usage: %s", usage_collector.get_summary())
        except Exception as exc:
            logger.warning("failed to log usage: %s", exc)

    ctx.add_shutdown_callback(_log_summary)

    await session.start(
        room=ctx.room,
        agent=Agent(instructions=system_prompt),
        room_input_options=RoomInputOptions(delete_room_on_close=True),
    )

    await session.generate_reply(instructions=greeting)


if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
        )
    )
