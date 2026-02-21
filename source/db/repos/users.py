from source.db.db import get_mysql_connection


def get_login_by_tg_id(tg_id):
    """
    Возвращает Nextcloud-логин пользователя по Telegram ID.
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_login FROM users WHERE tg_id = %s", (tg_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def save_login_to_db(tg_id, nc_login):
    """
    Сохраняет или обновляет соответствие Telegram ID и Nextcloud логина.
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (tg_id, nc_login) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE nc_login = VALUES(nc_login)",
        (tg_id, nc_login)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_user_list():
    """
    Возвращает список всех пользователей в формате [(tg_id, nc_login)].
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, nc_login FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [(row[0], row[1]) for row in rows]


def get_user_map():
    """
    Возвращает словарь:
    { nc_login: tg_id }

    Используется для отправки уведомлений назначенным пользователям.
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, nc_login FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[1]: row[0] for row in rows}
