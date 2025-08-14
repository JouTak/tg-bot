from source.db.db import get_mysql_connection
from source.config import BOT_LOG_TOPIC_ID

def get_message_thread_id(board_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT message_thread_id FROM board_log_topics WHERE board_id = %s", (board_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return row[0]
    else:
        return BOT_LOG_TOPIC_ID

def save_board_topic(board_id, thread_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO board_log_topics (board_id, message_thread_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE message_thread_id = VALUES(message_thread_id)
    """, (board_id, thread_id))
    conn.commit()
    cursor.close()
    conn.close()
