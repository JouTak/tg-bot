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

def save_login_to_db_with_token(tg_id, nc_login, nc_token):
    """
    Сохраняет или обновляет соответствие Telegram ID и Nextcloud логина.
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (tg_id, nc_login, nc_token) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE nc_login = VALUES(nc_login),"
        "nc_token = VALUES(nc_token)",
        (tg_id, nc_login, nc_token)
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

def get_users():
    """
    Возвращает словарь:
    {   username: nc_login
        password: nc_token }

    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_login, nc_token FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"username": row[0], "password": row[1]} for row in rows]

def save_login_token(id, token):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO login_token (tg_id, token) VALUES (%s, %s)",
        (id, token)
    )
    conn.commit()
    cursor.close()
    conn.close()

def delete_login_token(id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE IGNORE FROM login_token WHERE tg_id = %s",
        (id, )
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_token(id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM login_token WHERE tg_id = %s", (id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None

def get_nc_token(id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_token FROM users WHERE tg_id = %s", (id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None