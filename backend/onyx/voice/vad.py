import math
import struct
import time
from enum import Enum


class VadState(Enum):
    SILENCE = "silence"
    SPEAKING = "speaking"


class VoiceActivityDetector:
    """
    A lightweight, threshold-based Voice Activity Detector (VAD).
    Uses RMS (Root Mean Square) energy of PCM audio chunks to detect speech
    without relying on external heavy ML models or compiled C libraries.
    """

    def __init__(
        self,
        energy_threshold: float = 300.0,
        silence_timeout_s: float = 1.0,
        min_speech_duration_s: float = 0.2,
    ):
        self.energy_threshold = energy_threshold
        self.silence_timeout_s = silence_timeout_s
        self.min_speech_duration_s = min_speech_duration_s

        self.current_state = VadState.SILENCE
        self.last_speech_time = 0.0
        self.speech_start_time = 0.0

    def process_chunk(self, pcm_data: bytes, dynamic_silence_timeout_s: float | None = None) -> tuple[VadState, bool]:
        """
        Process a chunk of PCM audio and return the current state and a boolean
        indicating if a state transition just occurred.
        
        Args:
            pcm_data: Raw 16-bit PCM audio bytes.
            dynamic_silence_timeout_s: Optional override for the silence timeout.
            
        Returns:
            (VadState, is_transition)
        """
        if not pcm_data:
            return self.current_state, False

        # Calculate RMS energy of the chunk
        # Assuming 16-bit little-endian PCM
        count = len(pcm_data) // 2
        if count == 0:
            return self.current_state, False

        try:
            # unpack as little-endian signed short
            samples = struct.unpack(f"<{count}h", pcm_data)
        except struct.error:
            # If the chunk isn't perfectly aligned, just return current state
            return self.current_state, False

        sum_squares = sum(float(s) * float(s) for s in samples)
        rms = math.sqrt(sum_squares / count) if count > 0 else 0

        now = time.time()
        is_transition = False

        if rms > self.energy_threshold:
            # We detect audio energy
            self.last_speech_time = now
            if self.current_state == VadState.SILENCE:
                if self.speech_start_time == 0.0:
                    self.speech_start_time = now
                elif now - self.speech_start_time >= self.min_speech_duration_s:
                    self.current_state = VadState.SPEAKING
                    is_transition = True
        else:
            # We detect silence
            self.speech_start_time = 0.0
            if self.current_state == VadState.SPEAKING:
                timeout = dynamic_silence_timeout_s if dynamic_silence_timeout_s is not None else self.silence_timeout_s
                if now - self.last_speech_time >= timeout:
                    self.current_state = VadState.SILENCE
                    is_transition = True

        return self.current_state, is_transition

    def reset(self) -> None:
        """Reset the VAD state machine."""
        self.current_state = VadState.SILENCE
        self.last_speech_time = 0.0
        self.speech_start_time = 0.0

