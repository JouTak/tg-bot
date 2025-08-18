from __future__ import annotations
from typing import Dict, Set, Tuple
from source.db.db import get_mysql_connection


def ensure_tables():
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deadline_reminders (
            card_id BIGINT NOT NULL,
            login   VARCHAR(100) NOT NULL,
            stage   VARCHAR(32) NOT NULL,
            sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (card_id, login, stage)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_sent_map_for_period() -> Dict[Tuple[int, str], Set[str]]:
    ensure_tables()
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("SELECT card_id, login, stage FROM deadline_reminders")
    rows = cur.fetchall()
    cur.close(); conn.close()
    out: Dict[Tuple[int, str], Set[str]] = {}
    for card_id, login, stage in rows:
        out.setdefault((int(card_id), str(login)), set()).add(str(stage))
    return out

def mark_sent(card_id: int, login: str, stage: str) -> None:
    ensure_tables()
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO deadline_reminders (card_id, login, stage)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE sent_at = CURRENT_TIMESTAMP
    """, (card_id, login, stage))
    conn.commit()
    cur.close(); conn.close()
