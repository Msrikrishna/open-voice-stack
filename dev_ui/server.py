"""Local dev UI — mint LiveKit tokens, dispatch the agent, talk in the browser.

Run alongside `python -m agent.worker dev`:

    python -m dev_ui.server

Open http://127.0.0.1:8080.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from aiohttp import web
from dotenv import dotenv_values, load_dotenv
from livekit.api import AccessToken, LiveKitAPI, VideoGrants
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
from livekit.protocol.room import CreateRoomRequest

_DIR = Path(__file__).resolve().parent
_ENV_FILE = _DIR.parent / ".env"
load_dotenv(_ENV_FILE)

logging.basicConfig(level=logging.INFO, format="[dev_ui] %(message)s")
logger = logging.getLogger("dev_ui")

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
AGENT_NAME = os.environ.get("AGENT_NAME", "open-voice-agent")

# Built-in fallbacks if a key isn't present in .env or the environment.
_FALLBACKS = {
    "STT_BASE_URL": "http://localhost:8000/v1",
    "STT_MODEL":    "Systran/faster-whisper-base.en",
    "LLM_BASE_URL": "http://localhost:11434/v1",
    "LLM_MODEL":    "gemma4:e4b",
    "TTS_BASE_URL": "http://localhost:8880/v1",
    "TTS_MODEL":    "tts-1",
    "TTS_VOICE":    "af_bella",
}


def _current_defaults() -> dict[str, str]:
    """Re-read .env on every call so UI defaults track the file without
    needing to restart this server.
    """
    file_vals = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}

    def g(key: str) -> str:
        # Prefer the value currently in .env over what was loaded into the
        # process environment at startup. Falls back to env, then built-in.
        return file_vals.get(key) or os.environ.get(key) or _FALLBACKS[key]

    return {
        "stt_base_url": g("STT_BASE_URL"),
        "stt_model":    g("STT_MODEL"),
        "llm_base_url": g("LLM_BASE_URL"),
        "llm_model":    g("LLM_MODEL"),
        "tts_base_url": g("TTS_BASE_URL"),
        "tts_model":    g("TTS_MODEL"),
        "tts_voice":    g("TTS_VOICE"),
    }

# Override-able keys forwarded into room metadata for the agent to pick up.
_FORWARDED_KEYS = (
    "system_prompt", "greeting",
    "stt_base_url", "stt_model",
    "llm_base_url", "llm_model", "llm_temperature",
    "tts_base_url", "tts_model", "tts_voice",
)


async def _mint_token(request: web.Request) -> web.Response:
    body = await request.json()
    persona = {
        k: v for k, v in {k: body.get(k) for k in _FORWARDED_KEYS}.items()
        if v not in (None, "", "default")
    }

    room_name = f"dev-ui-{uuid.uuid4().hex[:8]}"
    metadata_str = json.dumps(persona)

    lkapi = LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    try:
        await lkapi.room.create_room(CreateRoomRequest(
            name=room_name,
            metadata=metadata_str,
            empty_timeout=60,
            max_participants=4,
        ))
        await lkapi.agent_dispatch.create_dispatch(CreateAgentDispatchRequest(
            agent_name=AGENT_NAME,
            room=room_name,
        ))
    finally:
        await lkapi.aclose()

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(f"user-{uuid.uuid4().hex[:6]}")
        .with_name("Dev User")
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .to_jwt()
    )

    logger.info("room=%s agent=%s overrides=%s", room_name, AGENT_NAME, list(persona))
    return web.json_response({
        "token": token,
        "url": LIVEKIT_URL,
        "room_name": room_name,
        "agent_name": AGENT_NAME,
    })


async def _defaults(_request: web.Request) -> web.Response:
    return web.json_response(_current_defaults())


async def _index(_request: web.Request) -> web.Response:
    return web.FileResponse(_DIR / "static" / "index.html")


def main() -> None:
    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_get("/api/defaults", _defaults)
    app.router.add_post("/api/token", _mint_token)
    app.router.add_static("/static", path=_DIR / "static", show_index=False)
    logger.info("dev UI on http://127.0.0.1:8080  (LiveKit=%s)", LIVEKIT_URL)
    web.run_app(app, host="127.0.0.1", port=8080, print=None)


if __name__ == "__main__":
    main()
