from source.config import FORUM_CHAT_ID
from source.connections.sender import send_message_limited
from source.db.repos.boards import get_message_thread_id

def send_log(text, board_id=None):
    message_thread_id = get_message_thread_id(board_id)
    send_message_limited(
        FORUM_CHAT_ID,
        text,
        parse_mode="Markdown",
        message_thread_id=message_thread_id
    )
