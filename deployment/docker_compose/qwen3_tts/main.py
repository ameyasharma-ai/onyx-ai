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
    instruct: Optional[str] = None

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
            
            # Generate a default voice clone prompt from 1s of silence
            logger.info("Generating default voice clone prompt...")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                import wave
                with wave.open(tmp.name, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(b'\x00' * 24000 * 1) # 1 sec silence
                
                with open(tmp.name, 'rb') as f:
                    default_wav_bytes = f.read()
                
                voice_prompts_cache["default"] = default_wav_bytes
                os.remove(tmp.name)
            logger.info("Default voice initialized as silence.")
            
            for voice_key, file_name in [("default_male", "default_male.wav"), ("default_female", "default_female.wav")]:
                if os.path.exists(file_name):
                    try:
                        with open(file_name, 'rb') as f:
                            voice_prompts_cache[voice_key] = f.read()
                        logger.info(f"{voice_key} voice initialized from {file_name}.")
                    except Exception as e:
                        logger.error(f"Failed to load {file_name}, using default silence: {e}")
                        voice_prompts_cache[voice_key] = voice_prompts_cache["default"]
                else:
                    logger.info(f"{file_name} not found, mapping {voice_key} to default voice.")
                    voice_prompts_cache[voice_key] = voice_prompts_cache["default"]
            
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
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
            
        # Instead of extracting tensors which can get corrupted during deepcopy,
        # we will just store the raw WAV bytes and pass the file to generate_voice_clone_streaming.
        voice_prompts_cache[voice_id] = audio_bytes
        return {"status": "success", "voice_id": voice_id}
    except Exception as e:
        logger.error(f"Failed to clone prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

import asyncio
generation_lock = asyncio.Lock()

async def audio_generator(text: str, vcp: dict, req_voice: str, instruct: Optional[str] = None):
    import copy
    import zlib
    import torch
    
    # stream returns chunks of numpy arrays
    try:
        # Start ffmpeg process
        import subprocess
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-f", "s16le",
            "-ar", "24000",
            "-ac", "1",
            "-i", "pipe:0",
            "-flush_packets", "1",
            "-f", "mp3",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        async def feed_ffmpeg():
            async with generation_lock:
                tmp_path = None
                if vcp is not None and isinstance(vcp, bytes):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(vcp)
                        tmp_path = tmp.name
                    
                try:
                    import re
                    sentences = re.split(r'(?<=[.!?,\n])\s+', text)
                    text_chunks = [s.strip() for s in sentences if s.strip()]
                    if not text_chunks:
                        text_chunks = [text]

                    loop = asyncio.get_event_loop()

                    for chunk in text_chunks:
                        def generate_chunk(c=chunk):
                            # Re-seed RNG for EACH chunk to force exactly the same voice timbre
                            voice_seed = zlib.crc32((req_voice or "default").encode('utf-8'))
                            torch.manual_seed(voice_seed)
                            if torch.cuda.is_available():
                                torch.cuda.manual_seed_all(voice_seed)
                                
                            # Use NON-streaming generation per clause
                            if tmp_path:
                                return model.generate_voice_clone(
                                    text=c,
                                    language="English",
                                    ref_audio=tmp_path,
                                    xvec_only=True,
                                    instruct=instruct
                                )
                            else:
                                return model.generate(
                                    text=c,
                                    language="English"
                                )

                        audio_arrays, sr = await loop.run_in_executor(None, generate_chunk)
                        
                        for audio_data in audio_arrays:
                            process.stdin.write((audio_data * 32767).astype(np.int16).tobytes())
                            await process.stdin.drain()
                except asyncio.CancelledError:
                    logger.info("feed_ffmpeg cancelled, exiting gracefully")
                except Exception as e:
                    logger.error(f"Error feeding ffmpeg: {e}")
                finally:
                    try:
                        process.stdin.close()
                        await process.stdin.wait_closed()
                    except Exception:
                        pass
                    if tmp_path:
                        import os
                        os.path.exists(tmp_path) and os.remove(tmp_path)

        # Start feeding in the background
        feed_task = asyncio.create_task(feed_ffmpeg())

        try:
            # Yield from stdout
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk

            await process.wait()
        except BaseException as e:
            logger.info(f"Stream interrupted or cancelled: {e}")
            try:
                process.kill()
            except ProcessLookupError:
                pass
            feed_task.cancel()
            raise
            
    except Exception as e:
        logger.error(f"Streaming failed: {e}")
        raise

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

    if req.instruct:
        logger.info(f"Synthesizing speech with instruct: {req.instruct}")

    return StreamingResponse(
        audio_generator(req.text, vcp, req.voice or "default", req.instruct), 
        media_type="audio/pcm"  # or audio/mpeg, depends on what frontend expects
    )
