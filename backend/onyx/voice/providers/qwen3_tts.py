import httpx
import logging
import os
from typing import AsyncGenerator, Dict, Any, List

from onyx.voice.interface import VoiceProviderInterface, StreamingSynthesizerProtocol, StreamingTranscriberProtocol

logger = logging.getLogger(__name__)

class Qwen3TTSProvider(VoiceProviderInterface):
    """
    Provider for Qwen3-TTS.
    Assumes a local instance of Qwen3-TTS is running in Docker and models are warm.
    """
    def __init__(self, api_base: str | None, custom_config: dict | None = None):
        self.api_base = api_base or os.getenv("QWEN3_TTS_URL", "http://qwen3_tts:8000")
        self.custom_config = custom_config or {}

    def transcribe(self, audio_data: bytes, audio_format: str) -> str:
        raise NotImplementedError("Qwen3-TTS is TTS only.")

    async def _ensure_voice_loaded(
        self, client: httpx.AsyncClient, voice: str | None
    ) -> str:
        """Ensure the voice clone prompt is cached in the TTS container.

        If ``voice`` is a file-store reference audio ID that isn't already
        cached, this fetches the audio bytes and pushes them to the container's
        ``/clone_prompt`` endpoint.  Returns the voice ID to use for synthesis
        (falls back to ``"default"`` when the voice cannot be loaded).
        """
        if not voice or voice == "default":
            return "default"

        # Fast path: already cached in the container
        try:
            resp = await client.get(
                f"{self.api_base}/voice_cached/{voice}", timeout=5.0
            )
            if resp.status_code == 200:
                return voice
        except Exception:
            pass

        # Not cached — load reference audio from file store and push
        try:
            from onyx.file_store.file_store import get_default_file_store

            file_store = get_default_file_store()
            file_io = file_store.read_file(voice, mode="b")
            audio_bytes = file_io.read()

            clone_resp = await client.post(
                f"{self.api_base}/clone_prompt",
                files={"file": (voice, audio_bytes, "audio/wav")},
                timeout=30.0,
            )
            clone_resp.raise_for_status()
            logger.info("Loaded voice '%s' into TTS container cache", voice)
            return voice
        except Exception as e:
            logger.warning(
                "Could not load voice '%s', falling back to default: %s",
                voice,
                e,
            )
            return "default"

    async def synthesize_stream(
        self, text: str, voice: str | None, speed: float
    ) -> AsyncGenerator[bytes, None]:
        import asyncio

        if not text.strip():
            return

        async with httpx.AsyncClient() as client:
            # Resolve the voice ONCE before processing.
            # This loads the persona's reference audio into the TTS container
            # cache if it isn't already there.
            resolved_voice = await self._ensure_voice_loaded(client, voice)

            async with client.stream(
                "POST",
                f"{self.api_base}/audio/speech",
                json={
                    "text": text,
                    "voice": resolved_voice,
                    "speed": speed,
                },
                timeout=None,
            ) as response:
                response.raise_for_status()
                async for audio_chunk in response.aiter_bytes(chunk_size=4096):
                    if audio_chunk:
                        yield audio_chunk

    async def validate_credentials(self) -> bool:
        # Check health endpoint
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/health", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    def get_available_voices(self) -> list[dict[str, str]]:
        # Voices are Persona-specific and resolved dynamically
        return [{"id": "default", "name": "Default Voice"}]

    def get_available_stt_models(self) -> list[str]:
        return []

    def get_available_tts_models(self) -> list[str]:
        return ["Qwen3-TTS-12Hz-0.6B-Base", "Qwen3-TTS-12Hz-0.6B-CustomVoice", "Qwen3-TTS-12Hz-1.7B-Base", "Qwen3-TTS-12Hz-1.7B-CustomVoice"]

    def supports_streaming_stt(self) -> bool:
        return False

    def supports_streaming_tts(self) -> bool:
        return True

    def create_streaming_transcriber(self) -> StreamingTranscriberProtocol:
        raise NotImplementedError("Qwen3-TTS does not support STT")

    def create_streaming_synthesizer(self, voice: str | None, speed: float) -> StreamingSynthesizerProtocol:
        class ChunkedStreamingSynthesizer(StreamingSynthesizerProtocol):
            def __init__(self, provider: VoiceProviderInterface, voice_id: str | None, speed_val: float):
                self.provider = provider
                self.voice = voice_id
                self.speed = speed_val
                self._text_buffer = ""
                self._stream_queue = asyncio.Queue()
                self._current_stream = None
            
            async def connect(self) -> None:
                pass
            
            async def send_text(self, text: str) -> None:
                self._text_buffer += text
                
                # Use same smart chunking logic
                import re
                raw_chunks = re.split(r'(?<=[.!?])(?:\s+|$)|(?<=\n)(?:\s+|$)', self._text_buffer)
                
                # We can't synthesize the VERY LAST chunk because the LLM might still be typing it.
                # So we keep the last chunk in the buffer, and synthesize all complete previous chunks 
                # that have accumulated >= 50 chars.
                if len(raw_chunks) <= 1:
                    return
                
                complete_text = ""
                # All except the last chunk (which is incomplete)
                for chunk in raw_chunks[:-1]:
                    if chunk.strip():
                        complete_text += (" " if complete_text else "") + chunk.strip()
                
                if len(complete_text) >= 50:
                    stream = self.provider.synthesize_stream(complete_text, self.voice, self.speed)
                    self._stream_queue.put_nowait(stream)
                    self._text_buffer = raw_chunks[-1].lstrip()
            
            async def receive_audio(self) -> bytes | None:
                while True:
                    if self._current_stream is None:
                        self._current_stream = await self._stream_queue.get()
                        if self._current_stream is None:
                            return None # EOF marker received

                    try:
                        return await anext(self._current_stream)
                    except StopAsyncIteration:
                        self._current_stream = None
                
            async def flush(self) -> None:
                if self._text_buffer.strip():
                    stream = self.provider.synthesize_stream(self._text_buffer.strip(), self.voice, self.speed)
                    self._stream_queue.put_nowait(stream)
                    self._text_buffer = ""
                self._stream_queue.put_nowait(None) # Signal EOF
                
            async def close(self) -> None:
                self._stream_queue.put_nowait(None)
                self._current_stream = None
                self._text_buffer = ""

        return ChunkedStreamingSynthesizer(self, voice, speed)

    async def validate_credentials(self) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_base}/health", timeout=5.0)
            response.raise_for_status()

    def get_available_voices(self) -> list[dict[str, str]]:
        return []

    def get_available_stt_models(self) -> list[dict[str, str]]:
        return []

    def get_available_tts_models(self) -> list[dict[str, str]]:
        return [{"id": "qwen3_tts", "name": "Qwen3-TTS"}]
