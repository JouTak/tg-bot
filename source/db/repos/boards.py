from typing import Optional

from sqlalchemy import select

from source.db.db import get_session
from source.config import BOT_LOG_TOPIC_ID
from source.migrations.models import BoardLogTopic


def get_message_thread_id(board_id: Optional[int]) -> Optional[int]:
    """Возвращает message_thread_id для доски или дефолтный топик."""
    if board_id is None:
        return BOT_LOG_TOPIC_ID

    with get_session() as session:
        topic = session.get(BoardLogTopic, board_id)
        return topic.message_thread_id if topic else BOT_LOG_TOPIC_ID


def save_board_topic(board_id: int, thread_id: int) -> None:
    """Привязывает топик к доске."""
    with get_session() as session:
        topic = session.get(BoardLogTopic, board_id)
        if topic:
            topic.message_thread_id = thread_id
        else:
            topic = BoardLogTopic(board_id=board_id, message_thread_id=thread_id)
            session.add(topic)
