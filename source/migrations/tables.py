from source.db.db import get_mysql_connection

def create_table_task_labels():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS task_labels (
          card_id INT NOT NULL,
          label VARCHAR(100) NOT NULL,
          PRIMARY KEY (card_id, label)
          ) ENGINE=InnoDB
            DEFAULT CHARSET=utf8mb4
            COLLATE=utf8mb4_unicode_ci
        """
    )
    cursor.close()
    conn.close()