// open-voice-stack dev console.
// Mints a token, dispatches the agent, and forwards provider overrides via
// room metadata so the worker can swap STT/LLM/TTS without restarting.

const DEFAULT_SYSTEM_PROMPT = `You are a helpful AI voice assistant.

# AI DISCLOSURE
- In your opening turn, mention you are an AI assistant.
- If asked directly, confirm in one sentence.

# VOICE OUTPUT — STRICT
- ONE short sentence per turn. After the sentence ends, STOP.
- No markdown, lists, code, headings, or emoji.
- Numbers as words.`;

const $ = (id) => document.getElementById(id);

const els = {
  status: $("status"),
  connect: $("connectBtn"),
  disconnect: $("disconnectBtn"),
  mute: $("muteBtn"),
  transcript: $("transcript"),
  micIndicator: $("micIndicator"),
  hint: $("hint"),
  sttBaseUrl: $("sttBaseUrl"),
  sttModel: $("sttModel"),
  llmBaseUrl: $("llmBaseUrl"),
  llmModel: $("llmModel"),
  llmTemperature: $("llmTemperature"),
  tempVal: $("tempVal"),
  ttsBaseUrl: $("ttsBaseUrl"),
  ttsModel: $("ttsModel"),
  ttsVoice: $("ttsVoice"),
  greeting: $("greeting"),
  systemPrompt: $("systemPrompt"),
};

els.systemPrompt.value = DEFAULT_SYSTEM_PROMPT;
els.llmTemperature.addEventListener("input", () => {
  els.tempVal.textContent = els.llmTemperature.value;
});

(async function loadDefaults() {
  try {
    const res = await fetch("/api/defaults");
    const d = await res.json();
    els.sttBaseUrl.value = d.stt_base_url || "";
    els.sttModel.value   = d.stt_model    || "";
    els.llmBaseUrl.value = d.llm_base_url || "";
    els.llmModel.value   = d.llm_model    || "";
    els.ttsBaseUrl.value = d.tts_base_url || "";
    els.ttsModel.value   = d.tts_model    || "";
    els.ttsVoice.value   = d.tts_voice    || "";
  } catch (err) {
    addBubble("error", `Failed to load defaults: ${err.message}`);
  }
})();

function setStatus(state, text) {
  els.status.className = state;
  els.status.textContent = text;
}

function addBubble(kind, text) {
  const div = document.createElement("div");
  div.className = `bubble ${kind}`;
  div.textContent = text;
  els.transcript.appendChild(div);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return div;
}

let room = null;

async function connect() {
  els.connect.disabled = true;
  setStatus("connecting", "connecting…");
  addBubble("system", "Requesting token + dispatching agent…");

  let tokenData;
  try {
    const res = await fetch("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        system_prompt: els.systemPrompt.value.trim(),
        greeting: els.greeting.value.trim(),
        stt_base_url: els.sttBaseUrl.value.trim(),
        stt_model:    els.sttModel.value.trim(),
        llm_base_url: els.llmBaseUrl.value.trim(),
        llm_model:    els.llmModel.value.trim(),
        llm_temperature: els.llmTemperature.value,
        tts_base_url: els.ttsBaseUrl.value.trim(),
        tts_model:    els.ttsModel.value.trim(),
        tts_voice:    els.ttsVoice.value.trim(),
      }),
    });
    if (!res.ok) throw new Error(`token endpoint ${res.status}`);
    tokenData = await res.json();
  } catch (err) {
    addBubble("error", `Failed to mint token: ${err.message}`);
    setStatus("error", "error");
    els.connect.disabled = false;
    return;
  }

  addBubble("system", `Joining room ${tokenData.room_name} → ${tokenData.agent_name}`);

  room = new LivekitClient.Room({ adaptiveStream: true, dynacast: true });

  room.on(LivekitClient.RoomEvent.Disconnected, () => {
    setStatus("disconnected", "disconnected");
    els.micIndicator.classList.remove("active");
    els.connect.disabled = false;
    els.disconnect.disabled = true;
    els.mute.disabled = true;
    els.mute.textContent = "Mute";
    els.mute.classList.remove("muted");
    els.hint.textContent = "Disconnected. Click Connect to start a new session.";
  });

  room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === LivekitClient.Track.Kind.Audio) {
      const el = track.attach();
      el.style.display = "none";
      document.body.appendChild(el);
    }
  });

  room.on(LivekitClient.RoomEvent.TranscriptionReceived, (segments, participant) => {
    const speaker = participant?.isLocal ? "user" : "agent";
    for (const seg of segments) {
      const id = `${participant?.identity || "x"}-${seg.id}`;
      let bubble = document.getElementById(id);
      if (!bubble) {
        bubble = addBubble(speaker, seg.text);
        bubble.id = id;
      } else {
        bubble.textContent = seg.text;
        els.transcript.scrollTop = els.transcript.scrollHeight;
      }
    }
  });

  try {
    await room.connect(tokenData.url, tokenData.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    setStatus("connected", "connected");
    els.micIndicator.classList.add("active");
    els.disconnect.disabled = false;
    els.mute.disabled = false;
    els.mute.textContent = "Mute";
    els.hint.textContent = "Speak whenever you are ready.";
  } catch (err) {
    addBubble("error", `Connect failed: ${err.message}`);
    setStatus("error", "error");
    els.connect.disabled = false;
  }
}

async function disconnect() {
  if (room) {
    await room.disconnect();
    room = null;
  }
}

async function toggleMute() {
  if (!room || !room.localParticipant) return;
  const currentlyEnabled = room.localParticipant.isMicrophoneEnabled;
  els.mute.disabled = true;
  try {
    await room.localParticipant.setMicrophoneEnabled(!currentlyEnabled);
    const nowMuted = !room.localParticipant.isMicrophoneEnabled;
    els.mute.textContent = nowMuted ? "Unmute" : "Mute";
    els.mute.classList.toggle("muted", nowMuted);
    els.micIndicator.classList.toggle("active", !nowMuted);
  } finally {
    els.mute.disabled = false;
  }
}

els.connect.addEventListener("click", connect);
els.disconnect.addEventListener("click", disconnect);
els.mute.addEventListener("click", toggleMute);
