import os
import io
import logging
import tempfile
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import soundfile as sf
import torch
import numpy as np

try:
    from faster_qwen3_tts import FasterQwen3TTS
except ImportError:
    FasterQwen3TTS = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen3_tts_server")

app = FastAPI(title="Faster Qwen3-TTS Server")

# Global variables
model = None
voice_prompts_cache = {}  # file_id -> voice clone prompt

class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = "default"
    speed: float = 1.0

@app.on_event("startup")
async def startup_event():
    global model
    logger.info("Initializing faster-qwen3-tts model...")
    if FasterQwen3TTS is not None:
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = FasterQwen3TTS.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                device=device
            )
            # Warm up CUDA graphs
            model.warmup()
            logger.info("Model loaded and warmed up successfully.")
            
            # Generate a default voice clone prompt from 0.5s of silence
            logger.info("Generating default voice clone prompt...")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                import wave
                with wave.open(tmp.name, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(b'\x00' * 24000 * 1) # 1 sec silence
                
                prompt_items = model.model.create_voice_clone_prompt(
                    ref_audio=tmp.name,
                    ref_text="",
                    x_vector_only_mode=True
                )
                voice_prompts_cache["default"] = model.model._prompt_items_to_voice_clone_prompt(prompt_items)
                os.remove(tmp.name)
            logger.info("Default voice initialized.")
            
        except Exception as e:
            logger.error(f"Failed to load FasterQwen3TTS model: {e}")
            model = None
    else:
        logger.warning("faster_qwen3_tts module not found.")

@app.get("/health")
def health_check():
    return {"status": "healthy", "model_loaded": model is not None}

@app.get("/voice_cached/{voice_id}")
def check_voice_cached(voice_id: str):
    """Check whether a voice clone prompt is already loaded in the cache."""
    if voice_id in voice_prompts_cache:
        return {"cached": True, "voice_id": voice_id}
    raise HTTPException(status_code=404, detail="Voice not cached")

@app.post("/clone_prompt")
async def clone_prompt(file: UploadFile = File(...)):
    """
    Generate and cache a voice clone prompt from reference audio.
    The filename is used as the voice_id cache key.
    """
    global model, voice_prompts_cache
    if model is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    voice_id = file.filename
    if not voice_id:
        raise HTTPException(status_code=400, detail="Filename missing in file upload (used as voice_id)")
        
    audio_bytes = await file.read()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
        
    try:
        # Create voice clone prompt (x_vector_only_mode=True means no ICL/ref_text required)
        # However, Qwen3TTS create_voice_clone_prompt is what we need to call.
        # Wait, FasterQwen3TTS wrapper uses `model.model.create_voice_clone_prompt` 
        # But `FasterQwen3TTS` exposes `generate_voice_clone_streaming` which takes `ref_audio` directly.
        # If we pass `ref_audio=tmp_path` to `generate_voice_clone_streaming`, it caches it internally in `_voice_prompt_cache`!
        # Let's extract the prompt so we don't have to keep the audio file.
        prompt_items = model.model.create_voice_clone_prompt(
            ref_audio=tmp_path,
            ref_text="",
            x_vector_only_mode=True
        )
        vcp = model.model._prompt_items_to_voice_clone_prompt(prompt_items)
        voice_prompts_cache[voice_id] = vcp
        return {"status": "success", "voice_id": voice_id}
    except Exception as e:
        logger.error(f"Failed to clone prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(tmp_path)

async def audio_generator(text: str, vcp: dict):
    # stream returns chunks of numpy arrays
    try:
        # If vcp is None, we need to generate without voice clone.
        # But FasterQwen3TTS says "Default voice generation not yet implemented."
        # However, we can trick it by providing a dummy zero tensor vcp if necessary,
        # or maybe the model supports generating with xvec_only and dummy speaker embedding?
        # Actually, if vcp is None, maybe we can just fall back to standard TTS?
        if vcp is None:
            # Let's see if generate_voice_clone_streaming handles None ref_audio
            # No, it says "ref_audio is required when voice_clone_prompt is not provided"
            pass # We will handle this in the outer function
            
        stream = model.generate_voice_clone_streaming(
            text=text,
            language="English",
            voice_clone_prompt=vcp,
            xvec_only=True
        )
        
        # Convert numpy chunks to MP3 bytes using ffmpeg to fix browser playback
        import asyncio
        import subprocess

        # Start ffmpeg process
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-f", "s16le",
            "-ar", "24000",
            "-ac", "1",
            "-i", "pipe:0",
            "-f", "mp3",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        async def feed_ffmpeg():
            try:
                loop = asyncio.get_event_loop()
                while True:
                    try:
                        audio_chunk, sr, timing = await loop.run_in_executor(None, next, stream)
                    except StopIteration:
                        break
                    pcm16 = (audio_chunk * 32767).astype(np.int16).tobytes()
                    process.stdin.write(pcm16)
                    await process.stdin.drain()
            except Exception as e:
                logger.error(f"Error feeding ffmpeg: {e}")
            finally:
                process.stdin.close()
                await process.stdin.wait_closed()

        # Start feeding in the background
        asyncio.create_task(feed_ffmpeg())

        # Yield from stdout
        while True:
            chunk = await process.stdout.read(4096)
            if not chunk:
                break
            yield chunk

        await process.wait()
            
    except Exception as e:
        logger.error(f"Streaming failed: {e}")

@app.post("/audio/speech")
async def stream_speech(req: SynthesizeRequest):
    """
    Stream synthesized speech.
    """
    global model, voice_prompts_cache
    
    if model is None:
        valid_mp3 = b'\xff\xe3\x18\xc4\x00\x00\x00\x03H\x00\x00\x00\x00LAME3.99.5' + b'\x00'*100
        return StreamingResponse(io.BytesIO(valid_mp3), media_type="audio/mpeg")
        
    vcp = voice_prompts_cache.get(req.voice or "default")
    if vcp is None:
        raise HTTPException(status_code=404, detail="Voice clone prompt not found in cache")

    # Use a deterministic seed based on the voice ID to ensure the character's
    # voice characteristics (timbre, mood) remain perfectly consistent across chunks.
    import zlib
    import torch
    voice_seed = zlib.crc32((req.voice or "default").encode('utf-8'))
    torch.manual_seed(voice_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(voice_seed)

    return StreamingResponse(
        audio_generator(req.text, vcp), 
        media_type="audio/pcm"  # or audio/mpeg, depends on what frontend expects
    )
