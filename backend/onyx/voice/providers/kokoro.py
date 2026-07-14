"""Kokoro ONNX voice provider for local Text-to-Speech.

Uses a locally running Kokoro ONNX HTTP server (OpenAI-compatible TTS API).
Default endpoint: http://localhost:8880 (configurable via KOKORO_URL).

The server must expose:
- ``POST /v1/audio/speech`` — OpenAI-compatible TTS endpoint
- ``GET /v1/models`` — list available models (used for health check)
"""

import asyncio
import os
from collections.abc import AsyncIterator

import aiohttp

from onyx.tracing.flows import LLMFlow
from onyx.tracing.llm_utils import traced_llm_call
from onyx.utils.logger import setup_logger
from onyx.voice.interface import VoiceProviderInterface

logger = setup_logger()

DEFAULT_KOKORO_URL = "http://localhost:8880"

# Timeout for TTS synthesis requests (seconds).
SYNTHESIZE_TIMEOUT_SECONDS = 120
# Timeout for health/validation checks (seconds).
HEALTH_TIMEOUT_SECONDS = 10
# Maximum retry attempts for transient failures.
MAX_RETRIES = 2
# Base delay between retries (seconds, doubled each attempt).
RETRY_BASE_DELAY = 0.5
# Chunk size for reading streamed audio responses.
STREAM_CHUNK_SIZE = 8192

# Kokoro built-in voices.
KOKORO_VOICES = [
    {"id": "af_heart", "name": "Heart (Female)"},
    {"id": "af_alloy", "name": "Alloy (Female)"},
    {"id": "af_aoede", "name": "Aoede (Female)"},
    {"id": "af_bella", "name": "Bella (Female)"},
    {"id": "af_jessica", "name": "Jessica (Female)"},
    {"id": "af_kore", "name": "Kore (Female)"},
    {"id": "af_nicole", "name": "Nicole (Female)"},
    {"id": "af_nova", "name": "Nova (Female)"},
    {"id": "af_river", "name": "River (Female)"},
    {"id": "af_sarah", "name": "Sarah (Female)"},
    {"id": "af_sky", "name": "Sky (Female)"},
    {"id": "am_adam", "name": "Adam (Male)"},
    {"id": "am_echo", "name": "Echo (Male)"},
    {"id": "am_eric", "name": "Eric (Male)"},
    {"id": "am_liam", "name": "Liam (Male)"},
    {"id": "am_michael", "name": "Michael (Male)"},
    {"id": "am_onyx", "name": "Onyx (Male)"},
    {"id": "bf_emma", "name": "Emma (British Female)"},
    {"id": "bf_isabella", "name": "Isabella (British Female)"},
    {"id": "bm_daniel", "name": "Daniel (British Male)"},
    {"id": "bm_fable", "name": "Fable (British Male)"},
    {"id": "bm_george", "name": "George (British Male)"},
    {"id": "bm_lewis", "name": "Lewis (British Male)"},
]


def _get_kokoro_url() -> str:
    """Resolve the Kokoro server URL from environment or default."""
    return os.environ.get("KOKORO_URL", DEFAULT_KOKORO_URL).rstrip("/")


def _get_default_kokoro_voice() -> str:
    """Resolve the default Kokoro voice from environment or default."""
    return os.environ.get("DEFAULT_KOKORO_VOICE", "af_heart")


def _get_default_kokoro_speed() -> float:
    """Resolve the default Kokoro speed from environment or default."""
    try:
        return float(os.environ.get("DEFAULT_KOKORO_SPEED", "1.0"))
    except (ValueError, TypeError):
        return 1.0


class KokoroProvider(VoiceProviderInterface):
    """Local TTS provider using a Kokoro ONNX HTTP server.

    This provider is TTS-only; all STT methods raise ``NotImplementedError``.

    The provider is designed so that future support for emotion and style
    parameters can be added via the ``custom_config`` dict without changing
    the interface.
    """

    def __init__(
        self,
        api_base: str | None = None,
        default_voice: str | None = None,
        default_speed: float | None = None,
        custom_config: dict[str, object] | None = None,
        **_kwargs: object,
    ) -> None:
        self.api_base = (api_base or _get_kokoro_url()).rstrip("/")
        self.default_voice = default_voice or _get_default_kokoro_voice()
        self.default_speed = default_speed or _get_default_kokoro_speed()
        # Extensibility: custom_config can carry future params like
        # emotion, style, language, etc.
        self.custom_config = custom_config or {}

    async def transcribe(self, audio_data: bytes, audio_format: str) -> str:
        """Not supported — Kokoro is a TTS-only provider."""
        raise NotImplementedError(
            "Kokoro is a text-to-speech provider and does not support STT."
        )

    async def synthesize_stream(
        self, text: str, voice: str | None = None, speed: float = 1.0
    ) -> AsyncIterator[bytes]:
        """Synthesize text to audio via the Kokoro OpenAI-compatible endpoint.

        Yields audio chunks (mp3 format) as they are received from the server.
        """
        final_voice = voice or self.default_voice
        final_speed = speed if speed != 1.0 else self.default_speed
        # Clamp speed to a reasonable range.
        final_speed = max(0.25, min(4.0, final_speed))

        url = f"{self.api_base}/v1/audio/speech"
        payload: dict[str, object] = {
            "model": "kokoro",
            "input": text,
            "voice": final_voice,
            "speed": final_speed,
            "response_format": "mp3",
        }

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with traced_llm_call(
                    flow=LLMFlow.TTS,
                    model="kokoro",
                    provider="kokoro",
                    input_messages=[{"role": "user", "content": text}],
                ):
                    async for chunk in self._do_synthesize(url, payload):
                        yield chunk
                return  # Success — exit retry loop.
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Kokoro synthesis attempt %s failed (%s), "
                        "retrying in %.1fs",
                        attempt + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Kokoro synthesis failed after {MAX_RETRIES + 1} attempts: "
            f"{last_exc}"
        )

    async def _do_synthesize(
        self, url: str, payload: dict[str, object]
    ) -> AsyncIterator[bytes]:
        """Execute a single synthesis request and stream audio chunks."""
        timeout = aiohttp.ClientTimeout(total=SYNTHESIZE_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Kokoro server returned HTTP {resp.status}: {body[:500]}"
                    )
                async for chunk in resp.content.iter_chunked(STREAM_CHUNK_SIZE):
                    if chunk:
                        yield chunk

    async def validate_credentials(self) -> None:
        """Validate connectivity by hitting the Kokoro models endpoint."""
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Kokoro OpenAI-compatible server exposes /v1/models.
                async with session.get(
                    f"{self.api_base}/v1/models"
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(
                            f"Kokoro server returned HTTP {resp.status}"
                        )
        except aiohttp.ClientError as exc:
            raise RuntimeError(
                f"Cannot connect to Kokoro server at {self.api_base}: {exc}"
            ) from exc

    def get_available_voices(self) -> list[dict[str, str]]:
        """Return Kokoro's built-in voice list."""
        return KOKORO_VOICES.copy()

    def get_available_stt_models(self) -> list[dict[str, str]]:
        """Kokoro is TTS-only; no STT models available."""
        return []

    def get_available_tts_models(self) -> list[dict[str, str]]:
        """Return the single Kokoro model."""
        return [{"id": "kokoro", "name": "Kokoro ONNX"}]
