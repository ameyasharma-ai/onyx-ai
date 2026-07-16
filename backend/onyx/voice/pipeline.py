import asyncio
import re
from collections.abc import AsyncIterator

from onyx.chat.models import AnswerStream
from onyx.server.query_and_chat.streaming_models import Packet
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Regex to split on semantic boundaries (sentence endings)
# We want to yield chunks that are natural to speak.
SEMANTIC_BOUNDARY_RE = re.compile(r"([.!?,\n]+)\s*")


async def semantic_chunker(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """
    Takes a raw token stream and yields complete semantic phrases/sentences.
    This minimizes TTFB (Time to First Byte) for TTS by sending smaller, complete
    phrases to the TTS engine as soon as they are available, rather than waiting
    for the entire LLM generation to finish.
    """
    buffer = ""
    async for token in token_stream:
        buffer += token
        
        # Fast path: check if we have a semantic boundary
        match = SEMANTIC_BOUNDARY_RE.search(buffer)
        if match:
            # We found a boundary. Extract the chunk up to and including the boundary
            end_idx = match.end()
            chunk = buffer[:end_idx].strip()
            
            # Only yield if it actually contains words (not just punctuation)
            if any(c.isalnum() for c in chunk):
                yield chunk
            
            # Keep the remainder in the buffer
            buffer = buffer[end_idx:].lstrip()
        elif len(buffer) > 120:
            # Fallback: if we haven't found a punctuation boundary for a long time,
            # force a break at the last space to prevent indefinite buffering and TTS delay.
            last_space = buffer.rfind(" ")
            if last_space != -1:
                chunk = buffer[:last_space].strip()
                if any(c.isalnum() for c in chunk):
                    yield chunk
                buffer = buffer[last_space:].lstrip()

    # Yield whatever is left in the buffer at the end of the stream
    buffer = buffer.strip()
    if buffer and any(c.isalnum() for c in buffer):
        yield buffer


async def extract_tokens_from_stream(answer_stream: AnswerStream, cancel_event: "threading.Event") -> AsyncIterator[str]:
    """
    Extracts raw text tokens from the structured AnswerStream.
    Ignores tool calls, citations, and metadata packets.
    Since answer_stream is a synchronous iterator (doing blocking network I/O),
    we must consume it in a separate thread and pipe it back to async.
    """
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _producer():
        try:
            for part in answer_stream:
                if cancel_event.is_set():
                    break
                if isinstance(part, Packet) and hasattr(part, "obj"):
                    if hasattr(part.obj, "type") and part.obj.type == "message_delta" and hasattr(part.obj, "content"):
                        # Use call_soon_threadsafe to safely put in queue from thread
                        if part.obj.content:
                            loop.call_soon_threadsafe(queue.put_nowait, part.obj.content)
        except Exception as e:
            logger.error(f"Error in LLM producer thread: {e}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None) # EOF sentinel

    # Start the blocking generator in a thread
    import threading
    threading.Thread(target=_producer, daemon=True).start()

    try:
        while True:
            token = await queue.get()
            if token is None:
                break
            yield token
    except asyncio.CancelledError:
        cancel_event.set()
        raise


async def pipeline_llm_to_tts(
    answer_stream: AnswerStream,
    synthesizer_func, # A factory/function that takes (text, voice, speed) and returns AsyncIterator[bytes]
    voice: str,
    speed: float,
    speech_instruction: str | None = None
) -> AsyncIterator[bytes]:
    """
    Orchestrates the entire backend-to-backend streaming loop:
    AnswerStream (LLM) -> Tokens -> Semantic Chunks -> TTS Audio Stream.
    
    Yields raw audio chunks ready to be sent over the WebSocket to the frontend.
    """
    import threading
    cancel_event = threading.Event()
    
    try:
        # 1. Extract raw string tokens from the LLM stream
        token_stream = extract_tokens_from_stream(answer_stream, cancel_event)
        
        # 2. Buffer tokens into semantic chunks (sentences/phrases)
        chunk_stream = semantic_chunker(token_stream)
        
        # 3. Stream each chunk to the TTS provider as soon as it's ready
        async for text_chunk in chunk_stream:
            logger.debug(f"Piping chunk to TTS: {text_chunk}")
            
            try:
                # synthesizer_func returns an async generator of bytes (fragments of an MP3)
                # The frontend decodeAudioData expects a COMPLETE valid MP3 file to decode.
                # Thus, we MUST buffer all fragments for this chunk and yield it as one message.
                if hasattr(synthesizer_func, "__code__") and "speech_instruction" in synthesizer_func.__code__.co_varnames:
                    audio_stream = synthesizer_func(text=text_chunk, voice=voice, speed=speed, speech_instruction=speech_instruction)
                else:
                    # For bound methods or others where inspection is tricky, just try/except or assume standard signature
                    try:
                        audio_stream = synthesizer_func(text=text_chunk, voice=voice, speed=speed, speech_instruction=speech_instruction)
                    except TypeError:
                        audio_stream = synthesizer_func(text=text_chunk, voice=voice, speed=speed)
                
                complete_audio = b""
                async for audio_bytes in audio_stream:
                    complete_audio += audio_bytes
                    
                if complete_audio:
                    yield complete_audio
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"TTS Synthesis failed for chunk '{text_chunk}': {e}")
                continue
    except asyncio.CancelledError:
        logger.info("pipeline_llm_to_tts was cancelled.")
        cancel_event.set()
        raise
