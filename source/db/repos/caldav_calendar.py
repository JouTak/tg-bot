from source.db.db import get_mysql_connection

def get_events_from_db():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT event_name FROM caldav_send_data")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(r[0] for r in rows)

def get_url_by_id(t_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM caldav_send_data WHERE id = %s", (t_id, ))
    rows = cursor.fetchone()
    cursor.close()
    conn.close()
    return rows[0]

def get_name_by_id(t_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT event_name FROM caldav_send_data WHERE id = %s", (t_id, ))
    rows = cursor.fetchone()
    cursor.close()
    conn.close()
    return rows[0]

def get_id_by_name(name):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM caldav_send_data WHERE event_name = %s", (name, ))
    rows = cursor.fetchone()
    cursor.close()
    conn.close()
    if rows is None:
        return None

    return rows[0]

def save_event_sends(name, url):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO caldav_send_data
          (event_name, url)
        VALUES (%s, %s)
        """,
        (name, url)
    )
    conn.commit()
    cursor.close()
    conn.close()

def delete_event_sends(name):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE IGNORE FROM caldav_send_data
        WHERE event_name = %s
        """,
        (name, )
    )
    conn.commit()
    cursor.close()
    conn.close()