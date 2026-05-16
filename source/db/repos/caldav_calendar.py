from source.db.db import get_mysql_connection

def get_events_from_db():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM caldav_send_data")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(r[0] for r in rows)

def save_event_sends(name):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO caldav_send_data
          (event_name)
        VALUES (%s)
        """,
        (name, )
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