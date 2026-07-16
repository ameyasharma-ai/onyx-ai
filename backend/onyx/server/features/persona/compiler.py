import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from onyx.db.models import Persona

logger = logging.getLogger(__name__)

def compile_persona_profile(persona: Persona) -> str:
    """
    Compiles the persona's personality, speaking style, and base system prompt 
    into a single optimized LLM instruction string.
    """
    system_prompt = persona.system_prompt or "You are a helpful assistant."
    
    parts = [system_prompt]
    
    if persona.personality_config:
        personality = persona.personality_config
        
        parts.append("\n--- PERSONALITY PROFILE ---")
        if personality.get("name"):
            parts.append(f"Name: {personality['name']}")
        if personality.get("short_description"):
            parts.append(f"Description: {personality['short_description']}")
        if personality.get("backstory"):
            parts.append(f"Backstory: {personality['backstory']}")
        if personality.get("core_personality"):
            parts.append(f"Core Personality: {personality['core_personality']}")
        
        for field in ["goals", "values", "beliefs", "likes", "dislikes", "humor", "traits", "weaknesses", "strengths", "motivations", "boundaries"]:
            if personality.get(field):
                parts.append(f"{field.capitalize()}: {personality[field]}")
                
        if personality.get("role") or personality.get("occupation"):
            parts.append(f"Role/Occupation: {personality.get('role', '')} {personality.get('occupation', '')}")
            
    if persona.speaking_style_config:
        style = persona.speaking_style_config
        parts.append("\n--- SPEAKING STYLE ---")
        for field in ["tone", "speech_speed", "energy", "confidence", "warmth", "accent", "vocabulary_complexity", "filler_words", "natural_pauses", "prosody", "intonation", "emotion", "speaking_notes"]:
            if style.get(field):
                parts.append(f"{field.replace('_', ' ').title()}: {style[field]}")
                
    if persona.personality_config and persona.personality_config.get("additional_instructions"):
        parts.append("\n--- ADDITIONAL INSTRUCTIONS ---")
        parts.append(persona.personality_config["additional_instructions"])
        
    compiled_profile = "\n".join(parts)
    return compiled_profile

def compile_speech_instruction(persona: Persona) -> str | None:
    """
    Compiles native speech parameters (tone, filler words, etc.) into an optimized 
    'instruct' string for faster-qwen3-tts.
    """
    if not persona.speaking_style_config:
        return None
        
    parts = []
    style = persona.speaking_style_config
    
    if style.get("tone"):
        parts.append(f"Tone: {style['tone']}")
    if style.get("emotion"):
        parts.append(f"Emotion: {style['emotion']}")
    if style.get("accent"):
        parts.append(f"Accent: {style['accent']}")
    if style.get("vocabulary_complexity"):
        parts.append(f"Vocabulary Complexity: {style['vocabulary_complexity']}")
    if style.get("filler_words"):
        parts.append(f"Filler Words: {style['filler_words']}")
    if style.get("natural_pauses"):
        parts.append(f"Pause Behavior: {style['natural_pauses']}")
    if style.get("speaking_notes"):
        parts.append(f"Notes: {style['speaking_notes']}")
        
    if not parts:
        return None
        
    return " | ".join(parts)

def compile_voice_profile(persona: Persona) -> dict[str, Any]:
    """
    Compiles the voice clone ID, speaking style parameters, and native speech
    instructions into a payload suitable for TTS engines (like Qwen3-TTS).
    """
    voice_id = persona.reference_audio_id or persona.voice_id
    if not voice_id and persona.voice_gender:
        if persona.voice_gender.lower() == "male":
            voice_id = "default_male"
        elif persona.voice_gender.lower() == "female":
            voice_id = "default_female"
            
    if not voice_id:
        voice_id = "default"
        
    speed = 1.0
    if persona.speaking_style_config and "speech_speed" in persona.speaking_style_config:
        speed_val = str(persona.speaking_style_config["speech_speed"]).lower()
        if "fast" in speed_val:
            speed = 1.2
        elif "slow" in speed_val:
            speed = 0.85
            
    return {
        "voice_id": voice_id,
        "speed": speed,
        "speech_instruction": compile_speech_instruction(persona),
        # Future-proofing for emotion/prosody parameters
        "emotion_baseline": persona.speaking_style_config.get("emotion") if persona.speaking_style_config else None
    }

def trigger_persona_compilation(persona: Persona, db_session: Session) -> Persona:
    """
    Executes the compiler on a Persona object, updates the compiled fields,
    and returns the mutated Persona.
    Does NOT commit the session (caller must do it).
    """
    try:
        persona.compiled_persona_profile = compile_persona_profile(persona)
        persona.compiled_voice_profile = compile_voice_profile(persona)
        persona.compilation_timestamp = datetime.utcnow()
        if persona.version is None:
            persona.version = 1
        else:
            persona.version += 1
            
        logger.info(f"Successfully compiled Persona Brain for Persona {persona.id} (Version {persona.version})")
    except Exception as e:
        logger.error(f"Failed to compile Persona Brain for Persona {persona.id}: {e}")
        
    return persona
