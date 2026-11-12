from source.config import FORUM_CHAT_ID
from source.connections.sender import send_message_limited
from source.db.repos.boards import get_message_thread_id
from source.db.repos.chats_config import resolve_task_chats

'''
def send_log(text, board_id=None, reply_markup=None):
    """
    Отправляет служебное сообщение в форум-чат.
    Если указана доска — сообщение отправляется в соответствующий топик.
    """
    message_thread_id = get_message_thread_id(board_id)
    send_message_limited(
        FORUM_CHAT_ID,
        text,
        message_thread_id=message_thread_id,
        reply_markup=reply_markup
    )
'''

def send_log(text, board_id=None, reply_markup=None, tag_ids=None):
    """
    Отправляет уведомление во все зарегистрированные беседы по их настройкам.
    """
    if board_id is None:
        # Сообщения без привязки к доске намеренно не рассылаются.
        return []

    sent = []
    for target in resolve_task_chats(board_id, tag_ids):
        kwargs = {"reply_markup": reply_markup}
        if target["topic_id"] is not None:
            kwargs["message_thread_id"] = int(target["topic_id"])
        message = send_message_limited(target["chat_id"], text, **kwargs)
        if message is not None:
            sent.append(message)
    return sent