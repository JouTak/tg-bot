from __future__ import annotations

from datetime import datetime
from typing import Dict, Set, Tuple, Optional

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


def get_last_sent_map() -> Dict[Tuple[int, str], Tuple[str, datetime]]:
    ensure_tables()
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.card_id, t.login, t.stage, t.sent_at
        FROM deadline_reminders AS t
        JOIN (
            SELECT card_id, login, MAX(sent_at) AS last_ts
            FROM deadline_reminders
            GROUP BY card_id, login
        ) AS m
          ON m.card_id = t.card_id
         AND m.login   = t.login
         AND m.last_ts = t.sent_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    out: Dict[Tuple[int, str], Tuple[str, datetime]] = {}
    for card_id, login, stage, sent_at in rows:
        out[(int(card_id), str(login))] = (str(stage), sent_at)
    return out


def get_sent_map_for_period() -> Dict[Tuple[int, str], Set[str]]:
    last = get_last_sent_map()
    out: Dict[Tuple[int, str], Set[str]] = {}
    for key, (stage, _) in last.items():
        out.setdefault(key, set()).add(stage)
    return out


def mark_sent(card_id: int, login: str, stage: str) -> None:
    ensure_tables()
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM deadline_reminders WHERE card_id = %s AND login = %s", (card_id, login))
    cur.execute("""
        INSERT INTO deadline_reminders (card_id, login, stage)
        VALUES (%s, %s, %s)
    """, (card_id, login, stage))
    conn.commit()
    cur.close()
    conn.close()


def reset_sent_for_card(card_id: int) -> None:
    ensure_tables()
    conn = get_mysql_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM deadline_reminders WHERE card_id = %s", (card_id,))
    conn.commit()
    cur.close()
    conn.close()
