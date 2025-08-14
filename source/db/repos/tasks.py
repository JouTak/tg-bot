from source.db.db import get_mysql_connection

def get_tasks_from_db(tg_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT card_id FROM tasks WHERE tg_id = %s", (tg_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(r[0] for r in rows)

def save_task_to_db(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks
          (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          title=VALUES(title),
          description=VALUES(description),
          board_id=VALUES(board_id),
          board_title=VALUES(board_title),
          stack_id=VALUES(stack_id),
          stack_title=VALUES(stack_title),
          duedate=VALUES(duedate)
        """,
        (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
    )
    conn.commit()
    cursor.close()
    conn.close()

def save_task_basic(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks
          (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          title=VALUES(title),
          description=VALUES(description),
          board_id=VALUES(board_id),
          board_title=VALUES(board_title),
          stack_id=VALUES(stack_id),
          stack_title=VALUES(stack_title),
          duedate=VALUES(duedate)
        """,
        (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
    )
    conn.commit()
    cursor.close()
    conn.close()

def save_task_assignee(card_id, nc_login):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO task_assignees
          (card_id, nc_login)
        VALUES (%s, %s)
        """,
        (card_id, nc_login)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_task_assignees(card_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_login FROM task_assignees WHERE card_id = %s", (card_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(row[0] for row in rows)

def get_saved_tasks():
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tasks")
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return {t['card_id']: t for t in tasks}

def update_task_in_db(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks SET
            title=%s, description=%s,
            board_id=%s, board_title=%s,
            stack_id=%s, stack_title=%s,
            duedate=%s
        WHERE card_id=%s
        """,
        (title, description, board_id, board_title, stack_id, stack_title, duedate, card_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_task_stats_map():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, comments_count, attachments_count FROM task_stats")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[0]: {"comments_count": row[1], "attachments_count": row[2]} for row in rows}

def upsert_task_stats(card_id: int, comments_count: int, attachments_count: int):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO task_stats (card_id, comments_count, attachments_count)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
          comments_count = VALUES(comments_count),
          attachments_count = VALUES(attachments_count)
        """,
        (card_id, comments_count, attachments_count)
    )
    conn.commit()
    cursor.close()
    conn.close()