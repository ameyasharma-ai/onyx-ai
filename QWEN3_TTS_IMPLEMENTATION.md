# Qwen3-TTS Implementation Guide

## Overview
PersonaLabs has officially transitioned from Chatterbox to **Qwen3-TTS** for all Text-to-Speech generation, including Live Voice Mode, Text Chat Speech, and Persona Voice Cloning.

## Architecture

The Qwen3-TTS implementation relies on a microservice architecture. 

1. **qwen3_tts Docker Container:**
   - Wraps the official `Qwen3-TTS` Python SDK behind a fast FastAPI HTTP interface.
   - Defaults to the `Qwen3-TTS-12Hz-0.6B-Base` model to optimize for extremely low TTFA (Time-To-First-Audio) latency, suitable for real-time Live Voice modes.
   - The model is loaded into VRAM on startup and remains permanently resident to prevent cold start delays.
   - Contains a `/clone_prompt` endpoint which caches the voice embedding dynamically.

2. **Qwen3TTSProvider (Backend):**
   - Implements `VoiceProviderInterface` (`backend/onyx/voice/providers/qwen3_tts.py`).
   - Hooks into Onyx's streaming pipeline via `ChunkedStreamingSynthesizer`.
   - On the first TTS request for a specific cloned persona, if the TTS service returns a 404 for the voice ID, the provider automatically downloads the reference `.wav` from the `file_store`, uploads it to `/clone_prompt`, and then safely retries the synthesis request. This ensures a completely invisible transition.

## Voice Cloning Lifecycle

1. **Upload:** User uploads a `.wav` file in the Persona Editor. The audio is saved in `file_store` and linked as `reference_audio_id` in the Persona.
2. **First Inference (Cache Miss):** 
   - `Qwen3TTSProvider` calls `/audio/speech` with the ID.
   - The container returns `404 Not Found`.
   - `Qwen3TTSProvider` reads the audio bytes from `file_store` and pushes them to `/clone_prompt`.
   - The container runs `create_voice_clone_prompt()` and caches it.
3. **Subsequent Inferences (Cache Hit):** 
   - `Qwen3TTSProvider` calls `/audio/speech` with the ID.
   - The container utilizes the cached prompt in VRAM, eliminating cloning overhead and ensuring sub-second TTS delivery.

## Configuration

The TTS model can be customized via the `QWEN3_TTS_MODEL` environment variable in the `docker-compose.yml`. Note that selecting models larger than `0.6B` may increase latency.
