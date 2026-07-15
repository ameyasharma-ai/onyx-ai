# Onyx Voice Architecture

## Overview

Onyx's voice subsystem provides Speech-to-Text (STT) and Text-to-Speech (TTS) capabilities
through a modular provider architecture. Multiple providers can be configured, but only one
STT provider and one TTS provider can be active (default) at any time.

## Provider Architecture

### Interface Layer

All voice providers implement `VoiceProviderInterface` (ABC) defined in
`backend/onyx/voice/interface.py`. The interface defines:

| Method | Purpose |
|--------|---------|
| `transcribe(audio_data, audio_format)` | One-shot STT (audio bytes → text) |
| `synthesize_stream(text, voice, speed)` | Streaming TTS (text → async audio chunks) |
| `validate_credentials()` | Health check / credential validation |
| `get_available_voices()` | List voices for TTS configuration |
| `get_available_stt_models()` | List STT model choices |
| `get_available_tts_models()` | List TTS model choices |
| `supports_streaming_stt()` | Whether native WebSocket STT is available |
| `supports_streaming_tts()` | Whether native WebSocket TTS is available |
| `create_streaming_transcriber()` | Factory for streaming STT sessions |
| `create_streaming_synthesizer()` | Factory for streaming TTS sessions |

Two protocol classes define streaming session interfaces:
- `StreamingTranscriberProtocol` — send audio chunks, receive transcript updates
- `StreamingSynthesizerProtocol` — send text, receive audio chunks

### Factory

`backend/onyx/voice/factory.py` maps `provider_type` strings to concrete implementations:

| provider_type | Class | Capabilities |
|---------------|-------|-------------|
| `openai` | `OpenAIVoiceProvider` | STT + TTS (streaming) |
| `azure` | `AzureVoiceProvider` | STT + TTS (streaming) |
| `elevenlabs` | `ElevenLabsVoiceProvider` | STT + TTS (streaming) |
| `whisper_cpp` | `WhisperCppProvider` | STT only (local) |
| `chatterbox` | `ChatterboxProvider` | TTS only (local) |

### Database Model

`VoiceProvider` table in `backend/onyx/db/models.py`:

| Column | Purpose |
|--------|---------|
| `provider_type` | Identifies the provider (e.g., "openai", "whisper_cpp") |
| `api_key` | Encrypted credential (nullable for keyless providers) |
| `api_base` | Server URL (used by local providers and custom endpoints) |
| `custom_config` | JSON for provider-specific settings |
| `stt_model` | Selected STT model |
| `tts_model` | Selected TTS model |
| `default_voice` | Default voice for TTS |
| `is_default_stt` | Whether this is the active STT provider |
| `is_default_tts` | Whether this is the active TTS provider |

## Request Flow

### STT (Speech-to-Text)

```
Browser microphone → WebSocket (PCM16 chunks)
    → websocket_api.py /voice/transcribe/stream
    → fetch_default_stt_provider(db)
    → factory.get_voice_provider(provider_db)
    → If streaming supported: create_streaming_transcriber()
    → Else: ChunkedTranscriber (batch REST calls)
    → Transcript JSON → Browser
```

Alternative REST path:
```
Browser → POST /voice/transcribe (multipart audio)
    → provider.transcribe(audio_data, format)
    → JSON {text: "..."}
```

### TTS (Text-to-Speech)

```
Browser → WebSocket /voice/synthesize/stream
    → fetch_default_tts_provider(db)
    → factory.get_voice_provider(provider_db)
    → If streaming TTS: create_streaming_synthesizer()
    → Else: provider.synthesize_stream() (chunked)
    → Binary audio chunks → Browser
```

Alternative REST path:
```
Browser → POST /voice/synthesize {text, voice, speed}
    → provider.synthesize_stream()
    → StreamingResponse (audio/mpeg)
```

## API Endpoints

### Admin (`/api/admin/voice/`)
- `GET /providers` — List all providers
- `POST /providers` — Create/update provider
- `DELETE /providers/{id}` — Delete provider
- `POST /providers/{id}/activate-stt` — Set as default STT
- `POST /providers/{id}/deactivate-stt` — Remove default STT
- `POST /providers/{id}/activate-tts` — Set as default TTS
- `POST /providers/{id}/deactivate-tts` — Remove default TTS
- `POST /providers/test` — Test connection
- `GET /providers/{id}/voices` — List voices
- `GET /voices?provider_type=X` — List voices by type

### User (`/api/voice/`)
- `GET /status` — Check STT/TTS availability
- `POST /transcribe` — One-shot STT
- `POST /synthesize` — Streaming TTS
- `PATCH /settings` — Update user preferences
- `POST /ws-token` — Get WebSocket auth token
- `WS /transcribe/stream` — Streaming STT
- `WS /synthesize/stream` — Streaming TTS

## Local Providers

### Keyless Provider Concept

Local providers (Whisper.cpp, Chatterbox) don't use API keys. The system identifies
"keyless" providers by type and bypasses API key checks in:
- Voice status endpoint
- Transcription endpoint
- Synthesis endpoint
- WebSocket handlers
- Admin test endpoint
- Voices listing endpoint

### Whisper.cpp (STT)

- Server: `whisper.cpp` with `--host` and `--port` flags
- Endpoint: `POST /inference` (multipart form, returns JSON with `text` field)
- Health: `GET /` returns 200
- Config: `WHISPER_CPP_URL` env var (default: `http://localhost:8080`)

### Chatterbox (TTS)

- Server: Resemble AI Chatterbox
- Endpoint: `POST /v1/audio/speech` (JSON body, streams audio)
- Health: `GET /v1/models` returns 200
- Config: `CHATTERBOX_URL` env var (default: `http://localhost:8880`)
- Features: Supports Zero-Shot Voice Cloning via `reference_audio_id` on Personas
- Speed: `DEFAULT_CHATTERBOX_SPEED` env var (default: 1.0)
- Voice: `DEFAULT_CHATTERBOX_VOICE` env var (default: default)

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WHISPER_CPP_URL` | `http://localhost:8080` | Whisper.cpp server URL |
| `CHATTERBOX_URL` | `http://localhost:8880` | Chatterbox server URL |
| `DEFAULT_CHATTERBOX_VOICE` | `default` | Default Chatterbox voice |
| `DEFAULT_CHATTERBOX_SPEED` | `1.0` | Default speech speed |
| `VOICE_DISABLE_STREAMING_STT` | `false` | Force chunked STT |
| `VOICE_DISABLE_STREAMING_FALLBACK` | `false` | Disable chunked fallback |

## Frontend Architecture

### Admin Page (`web/src/views/admin/VoicePage/`)
- `index.tsx` — Main page with STT and TTS model cards
- `shared.tsx` — Setup modal (adapts to provider type) and disconnect modal

### Voice Library (`web/src/lib/voice/`)
- `types.ts` — TypeScript interfaces
- `utils.ts` — Provider metadata (labels, icons, URLs, model lists)
- `svc.ts` — API client functions
- `hooks.ts` — SWR data hooks
