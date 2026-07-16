from uuid import UUID
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.engine.sql_engine import get_session_with_current_tenant_if_none
from onyx.db.models import Memory
from onyx.db.models import User
from onyx.utils.logger import setup_logger

logger = setup_logger()

MAX_MEMORIES_PER_USER = 10


class UserInfo(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "email": self.email,
        }


class UserMemoryContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID | None = None
    user_info: UserInfo
    user_preferences: str | None = None
    memories: tuple[str, ...] = ()

    def without_memories(self) -> "UserMemoryContext":
        """Return a copy with memories cleared but user info/preferences intact."""
        return UserMemoryContext(
            user_id=self.user_id,
            user_info=self.user_info,
            user_preferences=self.user_preferences,
            memories=(),
        )

    def as_formatted_list(self) -> list[str]:
        """Returns combined list of user info, preferences, and memories."""
        result = []
        if self.user_info.name:
            result.append(f"User's name: {self.user_info.name}")
        if self.user_info.role:
            result.append(f"User's role: {self.user_info.role}")
        if self.user_info.email:
            result.append(f"User's email: {self.user_info.email}")
        if self.user_preferences:
            result.append(f"User preferences: {self.user_preferences}")
        result.extend(self.memories)
        return result


def get_mem0_client():
    from mem0 import Memory as Mem0Memory
    from onyx.configs.app_configs import (
        POSTGRES_HOST,
        POSTGRES_PORT,
        POSTGRES_USER,
        POSTGRES_PASSWORD,
        POSTGRES_DB
    )
    from onyx.llm.factory import get_default_llm
    import urllib.parse
    
    password = urllib.parse.unquote_plus(POSTGRES_PASSWORD)
    mem0_config = {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "dbname": POSTGRES_DB,
                "user": POSTGRES_USER,
                "password": password,
                "host": POSTGRES_HOST,
                "port": int(POSTGRES_PORT),
                "collection_name": "mem0_memories",
                "embedding_model_dims": 384
            }
        },
        "llm": {
            "provider": "gemini",
            "config": {}
        },
        "embedder": {
            "provider": "fastembed",
            "config": {
                "model": "BAAI/bge-small-en-v1.5"
            }
        }
    }
    
    try:
        # Dynamically fetch the current default LLM configured in PersonaLabs
        default_llm = get_default_llm()
        if hasattr(default_llm, "config"):
            if getattr(default_llm.config, "model_name", None):
                mem0_config["llm"]["config"]["model"] = default_llm.config.model_name
            if getattr(default_llm.config, "api_key", None):
                mem0_config["llm"]["config"]["api_key"] = default_llm.config.api_key
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch default LLM for Mem0 client: {e}")

    # Patch FastEmbed to return lists instead of numpy arrays to fix psycopg2 adaptation errors
    from mem0.embeddings.fastembed import FastEmbedEmbedding
    original_embed = FastEmbedEmbedding.embed
    def patched_embed(self, text, memory_action=None):
        emb = original_embed(self, text, memory_action=memory_action)
        return emb.tolist() if hasattr(emb, 'tolist') else emb
    FastEmbedEmbedding.embed = patched_embed

    return Mem0Memory.from_config(mem0_config)


def get_memories(
    user: User, 
    db_session: Session, 
    persona_id: int | None = None,
    query: str | None = None
) -> UserMemoryContext:
    user_info = UserInfo(
        name=user.personal_name,
        role=user.personal_role,
        email=user.email,
    )

    user_preferences = None
    if user.user_preferences:
        user_preferences = user.user_preferences

    memories_list = []
    
    try:
        mem0 = get_mem0_client()
        user_id_str = str(user.id)

        def extract_memories(raw: object) -> list[str]:
            """Handle both list and dict (with 'results' key) return shapes."""
            if isinstance(raw, dict):
                raw = raw.get("results", [])
            return [r["memory"] for r in raw if isinstance(r, dict) and "memory" in r]

        # If query is provided, search for relevant memories. Otherwise get all.
        if query:
            global_results = mem0.search(query, filters={"user_id": user_id_str})
            memories_list.extend(extract_memories(global_results))

            if persona_id is not None:
                persona_results = mem0.search(
                    query,
                    filters={"user_id": user_id_str, "agent_id": str(persona_id)},
                )
                memories_list.extend(extract_memories(persona_results))
        else:
            global_results = mem0.get_all(filters={"user_id": user_id_str})
            memories_list.extend(extract_memories(global_results))

            if persona_id is not None:
                persona_results = mem0.get_all(
                    filters={"user_id": user_id_str, "agent_id": str(persona_id)}
                )
                memories_list.extend(extract_memories(persona_results))

    except Exception as e:
        logger.error(f"Failed to fetch memories from Mem0: {e}")
        memory_rows = db_session.scalars(
            select(Memory).where(Memory.user_id == user.id).order_by(Memory.id.asc())
        ).all()
        memories_list = [memory.memory_text for memory in memory_rows if memory.memory_text]

    # Remove duplicates but preserve order
    seen = set()
    memories = tuple(m for m in memories_list if not (m in seen or seen.add(m)))

    return UserMemoryContext(
        user_id=user.id,
        user_info=user_info,
        user_preferences=user_preferences,
        memories=memories,
    )


def add_memory(
    user_id: UUID,
    memory_text: str,
    db_session: Session | None = None,
) -> int:
    """Legacy function, kept for backwards compatibility."""
    with get_session_with_current_tenant_if_none(db_session) as db_session:
        try:
            mem0 = get_mem0_client()
            mem0.add(messages=memory_text, user_id=str(user_id))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to add memory to Mem0: {e}")
            raise e

        # Onyx legacy memory insertion is fully disabled
        return 0


def update_memory_at_index(
    user_id: UUID,
    index: int,
    new_text: str,
    db_session: Session | None = None,
) -> int | None:
    """Legacy function, kept for backwards compatibility."""
    with get_session_with_current_tenant_if_none(db_session) as db_session:
        memory_rows = db_session.scalars(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.id.asc())
        ).all()

        if index < 0 or index >= len(memory_rows):
            return None

        memory = memory_rows[index]
        
        try:
            mem0 = get_mem0_client()
            mem0.add(messages=new_text, user_id=str(user_id))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to add memory to Mem0: {e}")
            
        memory.memory_text = new_text
        db_session.commit()
        return memory.id
