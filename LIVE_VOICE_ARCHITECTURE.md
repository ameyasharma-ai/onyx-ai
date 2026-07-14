# Live Voice Mode Architecture

## 1. Current Architecture

Currently, Onyx's voice architecture is completely disjointed from the core chat pipeline. The pipeline operates sequentially with distinct network boundaries:

1. **STT Phase:** The frontend records audio, connects to `/api/voice/transcribe/stream` via WebSocket, and streams audio to the backend. The backend proxies this to the STT provider (e.g. Whisper.cpp) and returns the final transcript to the frontend.
2. **LLM Phase:** The frontend takes the final transcript text and submits it to the standard HTTP-based Chat streaming endpoint (`/api/chat/send-message`).
3. **TTS Phase:** As text chunks arrive from the LLM, the frontend batches them and makes requests to `/api/voice/synthesize/stream` to receive audio chunks.

### Files Involved
- **Backend:** `backend/onyx/server/manage/voice/websocket_api.py`, `backend/onyx/chat/process_message.py`
- **Frontend:** `web/src/lib/voice/` and standard chat components.

### Latency Bottlenecks
- **Sequential Networking:** Audio goes back and forth to the client 3 separate times.
- **Buffering:** TTS does not begin until the LLM yields enough tokens to form a sentence, and this is orchestrated over HTTP overhead.
- **No VAD Integration:** STT only ends when the user manually stops recording, adding artificial delays.
- **No Interruptions:** Once TTS starts playing, the frontend must wait for it to finish or manually cut it off.

---

## 2. Proposed Architecture

We will implement a unified **Voice Session Manager** over a single, full-duplex WebSocket connection (`/api/voice/live-session`). The backend will directly orchestrate the STT -> LLM -> TTS pipeline without returning intermediate state to the frontend, drastically reducing latency.

### Voice Request Lifecycle (Full Duplex)
1. **Connection:** Frontend opens WebSocket to `/api/voice/live-session` and begins streaming PCM microphone audio.
2. **VAD & STT:** Backend routes audio into a continuous STT stream. VAD (Voice Activity Detection) monitors amplitude/silence.
3. **LLM Trigger:** When VAD detects a silence threshold (e.g. 500ms), the backend finalizes the transcript and instantly kicks off the LLM generator.
4. **TTS Pipeline:** As the LLM yields tokens, a background task buffers them into semantic chunks (phrases) and pipes them directly to the TTS provider.
5. **Playback:** The synthesized audio chunks are piped straight back down the single WebSocket to the frontend for immediate playback.
6. **Interruption:** If VAD detects the user speaking while TTS is playing, the backend instantly aborts the TTS stream, signals the frontend to clear its audio buffers, and begins transcribing the new utterance.

### Modified & New Files
- **Backend (New):**
  - `backend/onyx/server/manage/voice/live_session.py`: The core WebSocket endpoint and orchestrator.
  - `backend/onyx/voice/vad.py`: Voice activity detection logic.
  - `backend/onyx/voice/pipeline.py`: The async pipeline connecting LLM streams to TTS streams.
- **Backend (Modified):**
  - `backend/onyx/chat/process_message.py`: Adjust to allow headless execution inside the voice orchestrator.
- **Frontend (New):**
  - `web/src/app/chat/live/page.tsx`: Dedicated Live Voice Mode UI.
  - `web/src/components/voice/LiveVoiceUI.tsx`: The modern floating orb animation component.
  - `web/src/lib/voice/LiveSessionClient.ts`: Full-duplex WebSocket client managing audio buffers.
- **Config (Modified):**
  - `.env` / `app_configs.py`: Add `VOICE_STREAMING_ENABLED`, `VOICE_SILENCE_TIMEOUT`, etc.

### Risk Analysis
- **Resource Exhaustion:** Long-lived WebSocket connections can leak memory if not properly cleaned up. 
  *Mitigation:* Implement strict timeouts, ping/pong heartbeats, and exception handlers ensuring graceful cleanup of TTS/LLM tasks on disconnect.
- **Interruption Race Conditions:** The user speaks while the LLM is midway generating a response.
  *Mitigation:* Use asyncio `Task.cancel()` on the LLM generator and TTS workers immediately upon VAD trigger.
- **UI Performance:** 60 FPS animations reacting to audio amplitude can cause React renders to block the main thread.
  *Mitigation:* Use WebGL/Canvas or CSS transforms driven directly by `requestAnimationFrame` outside of the React render cycle.

### Implementation Strategy
1. **Backend Foundation:** Implement the `LiveSessionManager` and the single unified WebSocket endpoint. Ensure it can receive audio, pipe to STT, pipe to LLM, pipe to TTS, and stream audio back.
2. **VAD & Interruptions:** Add Voice Activity Detection to automatically trigger the LLM upon silence, and abort TTS upon speech.
3. **Frontend Audio Client:** Build the `LiveSessionClient` capable of continuously recording audio and queueing incoming audio chunks for playback without clicking/popping.
4. **UI/UX:** Build the Live Mode interface with the animated orb, settings toggles, and state transitions (Listening, Thinking, Speaking).
5. **Testing & Polish:** Tune latency (chunk sizes, silence thresholds) to achieve the sub-500ms target.
