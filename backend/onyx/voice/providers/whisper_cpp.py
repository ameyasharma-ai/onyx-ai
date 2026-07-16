"""Whisper.cpp voice provider for local Speech-to-Text.

Uses a locally running Whisper.cpp HTTP server for transcription.
Default endpoint: http://localhost:8080 (configurable via WHISPER_CPP_URL).

The server must expose the ``/inference`` endpoint that accepts multipart
audio uploads and returns JSON with a ``text`` field.
"""

import asyncio
import os
import struct
from collections.abc import AsyncIterator

import aiohttp

from onyx.tracing.flows import LLMFlow
from onyx.tracing.llm_utils import traced_llm_call
from onyx.utils.logger import setup_logger
from onyx.voice.interface import VoiceProviderInterface

logger = setup_logger()

DEFAULT_WHISPER_CPP_URL = "http://localhost:8080"

# Timeout for individual transcription requests (seconds).
TRANSCRIBE_TIMEOUT_SECONDS = 60
# Timeout for health/validation checks (seconds).
HEALTH_TIMEOUT_SECONDS = 10
# Maximum retry attempts for transient failures.
MAX_RETRIES = 2
# Base delay between retries (seconds, doubled each attempt).
RETRY_BASE_DELAY = 0.5


def _get_whisper_cpp_url() -> str:
    """Resolve the Whisper.cpp server URL from environment or default."""
    return os.environ.get("WHISPER_CPP_URL", DEFAULT_WHISPER_CPP_URL).rstrip("/")


def _create_wav_header(
    data_length: int,
    sample_rate: int = 24000,
    channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """Create a WAV file header for raw PCM audio data."""
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_length,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_length,
    )
    return header


class WhisperCppProvider(VoiceProviderInterface):
    """Local STT provider using a Whisper.cpp HTTP server.

    This provider is STT-only; all TTS methods raise ``NotImplementedError``.
    """

    def __init__(
        self,
        api_base: str | None = None,
        stt_model: str | None = None,
        **_kwargs: object,
    ) -> None:
        self.api_base = (api_base or _get_whisper_cpp_url()).rstrip("/")
        self.stt_model = stt_model or "default"

    async def transcribe(self, audio_data: bytes, audio_format: str) -> str:
        """Transcribe audio via the Whisper.cpp ``/inference`` endpoint."""
        # Whisper.cpp server expects WAV; wrap raw PCM if needed.
        if audio_format == "pcm16":
            audio_data = _create_wav_header(len(audio_data)) + audio_data
            audio_format = "wav"

        filename = f"audio.{audio_format}"
        url = f"{self.api_base}/inference"

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with traced_llm_call(
                    flow=LLMFlow.STT,
                    model=self.stt_model,
                    provider="whisper_cpp",
                ):
                    return await self._do_transcribe(url, audio_data, filename)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Whisper.cpp transcription attempt %s failed (%s), "
                        "retrying in %.1fs",
                        attempt + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Whisper.cpp transcription failed after {MAX_RETRIES + 1} attempts: "
            f"{last_exc}"
        )

    async def _do_transcribe(
        self, url: str, audio_data: bytes, filename: str
    ) -> str:
        """Execute a single transcription request."""
        timeout = aiohttp.ClientTimeout(total=TRANSCRIBE_TIMEOUT_SECONDS)
        form = aiohttp.FormData()
        form.add_field(
            "file", audio_data, filename=filename, content_type="audio/wav"
        )
        # Whisper.cpp server parameters
        form.add_field("response_format", "json")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Whisper.cpp returned HTTP {resp.status}: {body[:500]}"
                    )
                data = await resp.json()
                return data.get("text", "").strip()

    async def synthesize_stream(
        self, text: str, voice: str | None = None, speed: float = 1.0, speech_instruction: str | None = None
    ) -> AsyncIterator[bytes]:
        """Not supported — Whisper.cpp is an STT-only provider."""
        raise NotImplementedError(
            "Whisper.cpp is a speech-to-text provider and does not support TTS."
        )
        # Make the function a valid async generator for type-checking.
        yield b""  # pragma: no cover

    async def validate_credentials(self) -> None:
        """Validate connectivity by hitting the Whisper.cpp health endpoint."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Whisper.cpp server responds to GET / with 200.
                async with session.get(self.api_base) as resp:
                    if resp.status != 200:
                        raise RuntimeError(
                            f"Whisper.cpp server returned HTTP {resp.status}"
                        )
        except aiohttp.ClientError as exc:
            raise RuntimeError(
                f"Cannot connect to Whisper.cpp server at {self.api_base}: {exc}"
            ) from exc

    def get_available_voices(self) -> list[dict[str, str]]:
        """Whisper.cpp is STT-only; no voices available."""
        return []

    def get_available_stt_models(self) -> list[dict[str, str]]:
        """Return the default model entry (actual model depends on server config)."""
        return [{"id": "default", "name": "Server Default"}]

    def get_available_tts_models(self) -> list[dict[str, str]]:
        """Whisper.cpp is STT-only; no TTS models available."""
        return []
