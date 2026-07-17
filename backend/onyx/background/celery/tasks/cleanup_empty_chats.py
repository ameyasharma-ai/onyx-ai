from datetime import datetime
from datetime import timedelta
from datetime import timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy import func

from onyx.db.engine import get_session_context_manager
from onyx.db.models import ChatMessage
from onyx.db.models import ChatSession
from onyx.utils.logger import setup_logger

logger = setup_logger()

@shared_task(
    name="cleanup_empty_chats_task",
    soft_time_limit=300,
    time_limit=360,
)
def cleanup_empty_chats_task() -> None:
    """Deletes chat sessions that have 0 messages and are older than 1 hour."""
    with get_session_context_manager() as db_session:
        # Find all chat sessions created more than 1 hour ago
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # We find sessions that have no related chat messages
        empty_session_ids = db_session.scalars(
            select(ChatSession.id)
            .outerjoin(ChatMessage, ChatMessage.chat_session_id == ChatSession.id)
            .where(ChatSession.time_created < one_hour_ago)
            .group_by(ChatSession.id)
            .having(func.count(ChatMessage.id) == 0)
        ).all()
        
        if not empty_session_ids:
            return
            
        logger.info(f"Deleting {len(empty_session_ids)} empty chat sessions...")
        for session_id in empty_session_ids:
            session = db_session.get(ChatSession, session_id)
            if session:
                db_session.delete(session)
        
        db_session.commit()
