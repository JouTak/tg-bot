from __future__ import annotations

from datetime import datetime
from typing import Dict, Tuple, Optional

from sqlalchemy import select, delete, func

from source.db.db import get_session
from source.migrations.models import DeadlineReminder


def get_last_sent_map() -> Dict[Tuple[int, str], Tuple[str, datetime]]:
    """
    Возвращает словарь { (card_id, login): (stage, sent_at) }
    для последнего напоминания каждой пары (card_id, login).
    """
    with get_session() as session:
        # Подзапрос: максимальный sent_at для каждой пары (card_id, login)
        subq = (
            select(
                DeadlineReminder.card_id,
                DeadlineReminder.login,
                func.max(DeadlineReminder.sent_at).label("last_ts")
            )
            .group_by(DeadlineReminder.card_id, DeadlineReminder.login)
            .subquery()
        )

        # Основной запрос: джойним с подзапросом
        stmt = (
            select(DeadlineReminder)
            .join(
                subq,
                (DeadlineReminder.card_id == subq.c.card_id) &
                (DeadlineReminder.login == subq.c.login) &
                (DeadlineReminder.sent_at == subq.c.last_ts)
            )
        )

        result = session.execute(stmt).scalars().all()

        return {
            (int(r.card_id), str(r.login)): (str(r.stage), r.sent_at)
            for r in result
        }


def mark_sent(card_id: int, login: str, stage: str) -> None:
    """Отмечает отправку напоминания (удаляет старые записи для пользователя)."""
    with get_session() as session:
        # Удаляем предыдущие записи для этой пары
        stmt = delete(DeadlineReminder).where(
            DeadlineReminder.card_id == card_id,
            DeadlineReminder.login == login
        )
        session.execute(stmt)

        # Добавляем новую запись
        reminder = DeadlineReminder(card_id=card_id, login=login, stage=stage)
        session.add(reminder)


def reset_sent_for_card(card_id: int) -> None:
    """Сбрасывает все напоминания для карточки."""
    with get_session() as session:
        stmt = delete(DeadlineReminder).where(DeadlineReminder.card_id == card_id)
        session.execute(stmt)
