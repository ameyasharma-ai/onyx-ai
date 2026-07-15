import asyncio
import json
import uuid
from typing import cast

from fastapi import APIRouter
from fastapi import Depends
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from sqlalchemy.orm import Session

from onyx.auth.users import current_user_from_websocket
from onyx.configs.app_configs import VOICE_INTERRUPT_ENABLED
from onyx.configs.app_configs import VOICE_SILENCE_TIMEOUT
from onyx.db.engine.sql_engine import get_session
from onyx.db.models import User
from onyx.db.voice import fetch_default_stt_provider
from onyx.db.voice import fetch_default_tts_provider
from onyx.server.query_and_chat.models import SendMessageRequest, ChatSessionCreationRequest
from onyx.utils.logger import setup_logger
from onyx.voice.factory import get_voice_provider
from onyx.voice.pipeline import pipeline_llm_to_tts
from onyx.voice.vad import VadState
from onyx.voice.vad import VoiceActivityDetector
from onyx.db.chat import get_chat_session_by_id
from onyx.db.persona import get_persona_by_id

logger = setup_logger()
router = APIRouter(prefix="/voice")

class VoiceSessionManager:
    def __init__(self, websocket: WebSocket, user: User, db_session: Session, chat_session_id: str | None, persona_id: int):
        self.websocket = websocket
        self.user = user
        self.db_session = db_session
        self.chat_session_id = chat_session_id
        self.persona_id = persona_id
        
        self.session_id = str(uuid.uuid4())
        self.valid_chat_id = None
        
        self.stt_provider = None
        self.tts_provider = None
        self.tts_db = None
        self.voice_id = None
        
        self.vad = VoiceActivityDetector(energy_threshold=1000.0, silence_timeout_s=VOICE_SILENCE_TIMEOUT)
        self.audio_queue = asyncio.Queue()
        self.stt_session = None
        
        self.current_transcript_buffer = ""
        self.utterance_buffer = bytearray()
        
        self.current_tts_task: asyncio.Task | None = None
        self.stt_send_task: asyncio.Task | None = None
        self.stt_recv_task: asyncio.Task | None = None
        self.disable_thinking = False
        
    async def initialize(self) -> bool:
        if self.chat_session_id:
            try:
                chat_session = get_chat_session_by_id(
                    chat_session_id=uuid.UUID(self.chat_session_id),
                    user_id=self.user.id,
                    db_session=self.db_session
                )
                if chat_session:
                    self.valid_chat_id = chat_session.id
            except Exception as e:
                logger.error(f"Invalid chat_session_id {self.chat_session_id}: {e}")
                
        # Resolve Persona and custom voice if available
        if self.persona_id > 0:
            persona = get_persona_by_id(self.persona_id, user=self.user, db_session=self.db_session)
            if persona and persona.voice_id:
                self.voice_id = persona.voice_id

        stt_db = fetch_default_stt_provider(self.db_session)
        self.tts_db = fetch_default_tts_provider(self.db_session)
        
        if not stt_db or not self.tts_db:
            await self.websocket.send_json({"type": "error", "message": "STT or TTS provider not configured"})
            await self.websocket.close()
            return False
            
        self.stt_provider = get_voice_provider(stt_db)
        self.tts_provider = get_voice_provider(self.tts_db)
        
        if self.stt_provider.supports_streaming_stt():
            self.stt_session = await self.stt_provider.create_streaming_transcriber(audio_format="pcm16")
            self.stt_send_task = asyncio.create_task(self._stt_sender())
            self.stt_recv_task = asyncio.create_task(self._stt_receiver())
            
        return True

    async def run(self):
        try:
            await self._ws_receiver()
        except Exception as e:
            logger.error(f"Live session error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def _ws_receiver(self):
        while True:
            try:
                message = await self.websocket.receive()
                
                if message["type"] == "websocket.disconnect":
                    break
                    
                if "bytes" in message:
                    pcm_data = message["bytes"]
                    if not self.stt_provider.supports_streaming_stt():
                        self.utterance_buffer.extend(pcm_data)
                    else:
                        await self.audio_queue.put(pcm_data)
                    
                    # Adaptive pause based on punctuation
                    is_end_of_sentence = False
                    if self.current_transcript_buffer:
                        txt = self.current_transcript_buffer.strip()
                        is_end_of_sentence = txt.endswith(('.', '?', '!', ',', ':', ';', '-'))
                    
                    # Shorten silence timeout if we likely finished a sentence
                    dynamic_timeout = 0.5 if is_end_of_sentence else VOICE_SILENCE_TIMEOUT
                    
                    # Run VAD
                    state, is_transition = self.vad.process_chunk(pcm_data, dynamic_silence_timeout_s=dynamic_timeout)
                    
                    if is_transition:
                        if state == VadState.SPEAKING:
                            logger.info(f"VAD: User started speaking")
                            await self.websocket.send_json({"type": "state", "state": "listening"})
                            
                            # INTERRUPT: Cancel any ongoing TTS/LLM generation!
                            if self.current_tts_task and not self.current_tts_task.done() and VOICE_INTERRUPT_ENABLED:
                                logger.info(f"VAD: Interrupting assistant!")
                                self.current_tts_task.cancel()
                                await self.websocket.send_json({"type": "interrupt"})
                                
                        elif state == VadState.SILENCE:
                            logger.info(f"VAD: User stopped speaking")
                            await self.websocket.send_json({"type": "state", "state": "thinking"})
                            
                            if not self.stt_provider.supports_streaming_stt():
                                try:
                                    final_text = await self.stt_provider.transcribe(bytes(self.utterance_buffer), audio_format="pcm16")
                                    self.current_transcript_buffer = final_text
                                except Exception as stt_err:
                                    logger.error(f"Non-streaming STT failed: {stt_err}")
                                    self.current_transcript_buffer = ""
                                self.utterance_buffer.clear()
                                
                            final_text = self.current_transcript_buffer.strip()
                            self.current_transcript_buffer = ""
                            
                            if final_text:
                                logger.info(f"User utterance: {final_text}")
                                await self.websocket.send_json({"type": "transcript_final", "text": final_text})
                                
                                # Launch LLM -> TTS pipeline
                                if self.current_tts_task and not self.current_tts_task.done():
                                    self.current_tts_task.cancel()
                                    
                                self.current_tts_task = asyncio.create_task(self._run_llm_and_tts(final_text))
                            else:
                                await self.websocket.send_json({"type": "state", "state": "idle"})
                                
                elif "text" in message:
                    data = json.loads(message["text"])
                    if data.get("action") == "stop":
                        if self.current_tts_task:
                            self.current_tts_task.cancel()
                        # Removed forced VAD state change; let the audio naturally trigger it.
                    elif data.get("action") == "settings":
                        self.disable_thinking = data.get("disable_thinking", False)
                        logger.info(f"Live voice settings updated: disable_thinking={self.disable_thinking}")

            except WebSocketDisconnect:
                break

    async def _stt_sender(self):
        try:
            while True:
                chunk = await self.audio_queue.get()
                if chunk is None:
                    break
                if self.stt_session:
                    await self.stt_session.send_audio(chunk)
        except asyncio.CancelledError:
            pass

    async def _stt_receiver(self):
        try:
            while True:
                if not self.stt_session:
                    break
                res = await self.stt_session.receive_transcript()
                if res is None:
                    break
                self.current_transcript_buffer = res.text
                await self.websocket.send_json({"type": "transcript_partial", "text": res.text})
        except asyncio.CancelledError:
            pass
            
    async def _run_llm_and_tts(self, text: str):
        from onyx.chat.process_message import handle_stream_message_objects
        
        await self.websocket.send_json({"type": "state", "state": "speaking"})
        
        additional_context = "Do not use <think> tags or chain-of-thought reasoning." if self.disable_thinking else None
        
        chat_session_info = ChatSessionCreationRequest(persona_id=self.persona_id) if not self.valid_chat_id else None
        req = SendMessageRequest(
            message=text,
            file_descriptors=[],
            chat_session_id=self.valid_chat_id,
            chat_session_info=chat_session_info,
            additional_context=additional_context
        )
        
        answer_stream = handle_stream_message_objects(new_msg_req=req, user=self.user)
        
        loop = asyncio.get_running_loop()
        def _stream_interceptor(stream):
            from onyx.chat.models import CreateChatSessionID
            for part in stream:
                if isinstance(part, CreateChatSessionID):
                    self.valid_chat_id = part.chat_session_id
                    logger.info(f"Live session mapped to new chat session ID: {self.valid_chat_id}")
                    
                    async def _send_chat_id():
                        try:
                            await self.websocket.send_json({"type": "chat_session_id", "chat_session_id": str(self.valid_chat_id)})
                        except Exception as e:
                            logger.error(f"Failed to send chat_session_id: {e}")
                    asyncio.run_coroutine_threadsafe(_send_chat_id(), loop)
                yield part
                
        intercepted_stream = _stream_interceptor(answer_stream)
        
        try:
            voice = self.voice_id or self.tts_db.default_voice
            speed = 1.0 
            
            audio_stream = pipeline_llm_to_tts(
                answer_stream=intercepted_stream,
                synthesizer_func=self.tts_provider.synthesize_stream,
                voice=voice,
                speed=speed
            )
            
            async for audio_chunk in audio_stream:
                await self.websocket.send_bytes(audio_chunk)
                
            await self.websocket.send_json({"type": "state", "state": "idle"})
            
        except asyncio.CancelledError:
            logger.info("TTS pipeline was cancelled due to interruption.")
        except Exception as e:
            logger.error(f"Error in TTS pipeline: {e}", exc_info=True)

    async def cleanup(self):
        logger.info(f"Cleaning up live session: {self.session_id}")
        if self.stt_send_task: self.stt_send_task.cancel()
        if self.stt_recv_task: self.stt_recv_task.cancel()
        if self.current_tts_task: self.current_tts_task.cancel()
        if self.stt_session:
            await self.stt_session.close()


@router.websocket("/live-session")
async def websocket_live_session(
    websocket: WebSocket,
    chat_session_id: str | None = None,
    persona_id: int = 0,
    _user: User = Depends(current_user_from_websocket),
    db_session: Session = Depends(get_session),
):
    """
    Unified full-duplex WebSocket for Ultra-low latency Live Voice Mode.
    Receives PCM audio chunks from frontend, orchestrates STT -> VAD -> LLM,
    and returns synthesized text chunks to the frontend for native TTS.
    """
    await websocket.accept()
    manager = VoiceSessionManager(websocket, _user, db_session, chat_session_id, persona_id)
    
    if await manager.initialize():
        await manager.run()
