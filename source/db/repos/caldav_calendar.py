from typing import Optional, Set

from sqlalchemy import select, delete

from source.db.db import get_session
from source.migrations.models import CalDavSendData


def get_events_from_db() -> Set[str]:
    """Возвращает set строк в формате {tg_id}_{event_name} из БД."""
    with get_session() as session:
        stmt = select(CalDavSendData.tg_id, CalDavSendData.event_name)
        result = session.execute(stmt).all()
        return {f"{row.tg_id}_{row.event_name}" for row in result}


def get_url_by_id(t_id: int) -> Optional[str]:
    """Возвращает URL события по ID."""
    with get_session() as session:
        event = session.get(CalDavSendData, t_id)
        return event.url if event else None


def get_name_by_id(t_id: int) -> Optional[str]:
    """Возвращает event_name по ID."""
    with get_session() as session:
        event = session.get(CalDavSendData, t_id)
        return event.event_name if event else None


def get_id_by_name(name: str) -> Optional[int]:
    """Возвращает ID события по event_name."""
    with get_session() as session:
        stmt = select(CalDavSendData).where(CalDavSendData.event_name == name)
        event = session.execute(stmt).scalar_one_or_none()
        return event.id if event else None


def save_event_sends(name: str, tg_id: int, event_name: str, url: str) -> None:
    """Сохраняет новое событие (игнорирует дубликаты)."""
    with get_session() as session:
        # Проверяем существование
        stmt = select(CalDavSendData).where(CalDavSendData.event_name == event_name, CalDavSendData.tg_id == tg_id)
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            event = CalDavSendData(name=name, tg_id=tg_id, event_name=event_name, url=url)
            session.add(event)


def delete_event_sends(name: str) -> None:
    """Удаляет событие по event_name."""
    with get_session() as session:
        stmt = delete(CalDavSendData).where(CalDavSendData.event_name == name)
        session.execute(stmt)
