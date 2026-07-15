# Local Voice Providers Implementation Guide

This document outlines the setup, configuration, and architecture of the newly integrated **Local Offline Voice Providers** in Onyx.

Onyx now officially supports entirely offline Speech-to-Text (STT) and Text-to-Speech (TTS) using local, open-source models. This ensures absolute privacy and zero external API costs.

## 1. Supported Providers

1. **Whisper.cpp (STT)**
   - Engine: [ggerganov/whisper.cpp](https://github.com/ggerganov/whisper.cpp)
   - Default Model: `ggml-base.en.bin`
   - Role: Fast, highly accurate offline speech recognition.

2. **Chatterbox (TTS)**
   - Engine: [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox)
   - Default Model: `chatterbox`
   - Role: High-quality, low-latency offline speech synthesis with multiple built-in voices.

---

## 2. Architecture & Networking

Both providers run as dedicated Docker containers alongside the main Onyx stack, communicating with the `api_server` via the internal Docker network.

- **Frontend (Browser):** Records audio and sends it to the Onyx `api_server` via the standard websocket/HTTP endpoints.
- **Backend (`api_server`):** Bypasses API key validation for these specific "keyless" providers and proxies the audio data directly to the local containers.
- **Voice Containers:** Process the audio entirely on the host machine and return the transcript/audio chunks to the backend.

### SSRF Protection Bypass
Because the Onyx backend enforces strict Server-Side Request Forgery (SSRF) protection, requests to `localhost` are blocked. To securely bypass this, the backend identifies `whisper_cpp` and `chatterbox` as trusted local provider types and permits them to resolve to private Docker network IPs. 

---

## 3. Configuration & Deployment

### Environment Variables
The local providers are pre-configured in `deployment/docker_compose/.env`:

```env
# Local STT
WHISPER_CPP_URL=http://whisper_cpp:8080
WHISPER_CPP_MODEL=ggml-base.en.bin

# Local TTS
CHATTERBOX_URL=http://chatterbox:8880
DEFAULT_CHATTERBOX_VOICE=default
```

### Docker Compose
The providers are initialized in `docker-compose.yml`:
- **`whisper_cpp_init`**: An Alpine container that automatically downloads the `ggml-base.en.bin` model to a shared volume on first boot.
- **`whisper_cpp`**: The primary STT server exposing port `8081` on the host (internal `8080`).
- **`chatterbox`**: The primary TTS server exposing port `8880` on the host.

*(Note: The heavy ML libraries and models are downloaded automatically during the Docker build and initialization phases).*

---

## 4. Admin Setup

Once the Onyx stack is running, administrators can enable the local providers via the UI:

1. Navigate to **Admin Panel > Configuration > Voice**.
2. Select **Whisper.cpp** under Speech-to-Text.
   - **Server URL:** `http://whisper_cpp:8080`
3. Select **Chatterbox** under Text-to-Speech.
   - **Server URL:** `http://chatterbox:8880`
4. Click **Connect**. The backend will validate the endpoints and set them as the default active voice providers.

*(Important: Always use the Docker service names (`whisper_cpp` and `chatterbox`) rather than `localhost` to ensure the internal network routes correctly).*
