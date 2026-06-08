from datetime import datetime
from typing import Optional, Dict, Set, List, Tuple, Any

from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload

from source.db.db import get_session
from source.migrations.models import (
    Task, TaskAssignee, TaskStat, TaskLabel,
    TaskAttachment, TaskComment, DeadlineReminder
)


def get_tasks_from_db(tg_id: int) -> Set[int]:
    """Возвращает set card_id задач пользователя."""
    # Этот метод не используется, но оставлен для совместимости
    with get_session() as session:
        stmt = select(Task.card_id)
        result = session.execute(stmt).scalars().all()
        return set(result)


def save_task_to_db(
    card_id: int, title: str, description: str,
    board_id: int, board_title: str,
    stack_id: int, stack_title: str,
    prev_stack_id: Optional[int], prev_stack_title: Optional[str],
    next_stack_id: Optional[int], next_stack_title: Optional[str],
    duedate: Optional[datetime], done: Optional[datetime], etag: Optional[str]
) -> None:
    """Сохраняет или обновляет задачу."""
    with get_session() as session:
        task = session.get(Task, card_id)
        if task:
            task.title = title
            task.description = description
            task.board_id = board_id
            task.board_title = board_title
            task.stack_id = stack_id
            task.stack_title = stack_title
            task.prev_stack_id = prev_stack_id
            task.prev_stack_title = prev_stack_title
            task.next_stack_id = next_stack_id
            task.next_stack_title = next_stack_title
            task.duedate = duedate
            task.done = done
            task.etag = etag
        else:
            task = Task(
                card_id=card_id, title=title, description=description,
                board_id=board_id, board_title=board_title,
                stack_id=stack_id, stack_title=stack_title,
                prev_stack_id=prev_stack_id, prev_stack_title=prev_stack_title,
                next_stack_id=next_stack_id, next_stack_title=next_stack_title,
                duedate=duedate, done=done, etag=etag
            )
            session.add(task)


def update_task_in_db(
    card_id: int, title: str, description: str,
    board_id: int, board_title: str,
    stack_id: int, stack_title: str,
    prev_stack_id: Optional[int], prev_stack_title: Optional[str],
    next_stack_id: Optional[int], next_stack_title: Optional[str],
    duedate: Optional[datetime], done: Optional[datetime], etag: Optional[str]
) -> None:
    """Обновляет задачу."""
    with get_session() as session:
        task = session.get(Task, card_id)
        if task:
            task.title = title
            task.description = description
            task.board_id = board_id
            task.board_title = board_title
            task.stack_id = stack_id
            task.stack_title = stack_title
            task.prev_stack_id = prev_stack_id
            task.prev_stack_title = prev_stack_title
            task.next_stack_id = next_stack_id
            task.next_stack_title = next_stack_title
            task.duedate = duedate
            task.done = done
            task.etag = etag


def save_task_assignee(card_id: int, nc_login: str) -> None:
    """Добавляет назначенного пользователя к задаче."""
    with get_session() as session:
        stmt = select(TaskAssignee).where(
            TaskAssignee.card_id == card_id,
            TaskAssignee.nc_login == nc_login
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            assignee = TaskAssignee(card_id=card_id, nc_login=nc_login)
            session.add(assignee)


def delete_task_assignee(card_id: int, nc_login: str) -> None:
    """Удаляет назначенного пользователя."""
    with get_session() as session:
        stmt = delete(TaskAssignee).where(
            TaskAssignee.card_id == card_id,
            TaskAssignee.nc_login == nc_login
        )
        session.execute(stmt)


def get_task_assignees(card_id: int) -> Set[str]:
    """Возвращает set логинов назначенных пользователей."""
    with get_session() as session:
        stmt = select(TaskAssignee.nc_login).where(TaskAssignee.card_id == card_id)
        result = session.execute(stmt).scalars().all()
        return set(result)


def get_saved_tasks() -> Dict[int, Dict[str, Any]]:
    """Возвращает словарь { card_id: task_dict } для всех задач."""
    with get_session() as session:
        stmt = select(Task)
        tasks = session.execute(stmt).scalars().all()
        return {
            t.card_id: {
                'card_id': t.card_id,
                'title': t.title,
                'description': t.description,
                'board_id': t.board_id,
                'board_title': t.board_title,
                'stack_id': t.stack_id,
                'stack_title': t.stack_title,
                'prev_stack_id': t.prev_stack_id,
                'prev_stack_title': t.prev_stack_title,
                'next_stack_id': t.next_stack_id,
                'next_stack_title': t.next_stack_title,
                'duedate': t.duedate,
                'done': t.done,
                'etag': t.etag,
            }
            for t in tasks
        }


def get_saved_tasks_for_deadlines() -> List[Dict[str, Any]]:
    """Возвращает задачи с назначенными пользователями для проверки дедлайнов."""
    with get_session() as session:
        stmt = (
            select(Task)
            .join(TaskAssignee)
            .options(joinedload(Task.assignees))
        )
        tasks = session.execute(stmt).unique().scalars().all()

        result = []
        for t in tasks:
            task_dict = {
                'card_id': t.card_id,
                'title': t.title,
                'description': t.description,
                'board_id': t.board_id,
                'board_title': t.board_title,
                'stack_id': t.stack_id,
                'stack_title': t.stack_title,
                'prev_stack_id': t.prev_stack_id,
                'prev_stack_title': t.prev_stack_title,
                'next_stack_id': t.next_stack_id,
                'next_stack_title': t.next_stack_title,
                'duedate': t.duedate,
                'done': t.done,
                'etag': t.etag,
                'assigned_logins': [a.nc_login for a in t.assignees],
            }
            result.append(task_dict)
        return result


def get_tasks_from_users(login: str) -> List[Dict[str, Any]]:
    """Возвращает задачи конкретного пользователя."""
    with get_session() as session:
        stmt = (
            select(Task)
            .join(TaskAssignee)
            .where(TaskAssignee.nc_login == login)
        )
        tasks = session.execute(stmt).scalars().all()

        return [
            {
                'card_id': t.card_id,
                'title': t.title,
                'description': t.description,
                'board_id': t.board_id,
                'board_title': t.board_title,
                'stack_id': t.stack_id,
                'stack_title': t.stack_title,
                'prev_stack_id': t.prev_stack_id,
                'prev_stack_title': t.prev_stack_title,
                'next_stack_id': t.next_stack_id,
                'next_stack_title': t.next_stack_title,
                'duedate': t.duedate,
                'done': t.done,
                'etag': t.etag,
            }
            for t in tasks
        ]


def get_task_stats_map() -> Dict[int, Dict[str, int]]:
    """Возвращает словарь { card_id: {comments_count, attachments_count} }."""
    with get_session() as session:
        stmt = select(TaskStat)
        stats = session.execute(stmt).scalars().all()
        return {
            s.card_id: {
                "comments_count": s.comments_count,
                "attachments_count": s.attachments_count
            }
            for s in stats
        }


def get_task_stat(card_id: int) -> List[int]:
    """Возвращает [comments_count, attachments_count] для задачи."""
    with get_session() as session:
        stat = session.get(TaskStat, card_id)
        if stat:
            return [stat.comments_count, stat.attachments_count]
        return [0, 0]


def upsert_task_stats(card_id: int, comments_count: int, attachments_count: int) -> None:
    """Создаёт или обновляет статистику задачи."""
    with get_session() as session:
        stat = session.get(TaskStat, card_id)
        if stat:
            stat.comments_count = comments_count
            stat.attachments_count = attachments_count
        else:
            stat = TaskStat(
                card_id=card_id,
                comments_count=comments_count,
                attachments_count=attachments_count
            )
            session.add(stat)


def save_task_label(card_id: int, label: str) -> None:
    """Добавляет метку к задаче."""
    with get_session() as session:
        stmt = select(TaskLabel).where(
            TaskLabel.card_id == card_id,
            TaskLabel.label == label
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            task_label = TaskLabel(card_id=card_id, label=label)
            session.add(task_label)


def delete_task_label(card_id: int, label: str) -> None:
    """Удаляет метку задачи."""
    with get_session() as session:
        stmt = delete(TaskLabel).where(
            TaskLabel.card_id == card_id,
            TaskLabel.label == label
        )
        session.execute(stmt)


def get_task_labels(card_id: int) -> Set[str]:
    """Возвращает set меток задачи."""
    with get_session() as session:
        stmt = select(TaskLabel.label).where(TaskLabel.card_id == card_id)
        result = session.execute(stmt).scalars().all()
        return set(result)


def save_task_attachment(card_id: int, file_id: int) -> None:
    """Добавляет вложение к задаче."""
    with get_session() as session:
        stmt = select(TaskAttachment).where(
            TaskAttachment.card_id == card_id,
            TaskAttachment.file_id == file_id
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            attachment = TaskAttachment(card_id=card_id, file_id=file_id)
            session.add(attachment)


def delete_task_attachment(card_id: int, file_id: int) -> None:
    """Удаляет вложение задачи."""
    with get_session() as session:
        stmt = delete(TaskAttachment).where(
            TaskAttachment.card_id == card_id,
            TaskAttachment.file_id == file_id
        )
        session.execute(stmt)


def get_task_attachments(card_id: int) -> Set[int]:
    """Возвращает set file_id вложений задачи."""
    with get_session() as session:
        stmt = select(TaskAttachment.file_id).where(TaskAttachment.card_id == card_id)
        result = session.execute(stmt).scalars().all()
        return set(result)


def save_task_comment(card_id: int, comment_id: int) -> None:
    """Добавляет комментарий к задаче."""
    with get_session() as session:
        stmt = select(TaskComment).where(
            TaskComment.card_id == card_id,
            TaskComment.comment_id == comment_id
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            comment = TaskComment(card_id=card_id, comment_id=comment_id)
            session.add(comment)


def delete_task_comment(card_id: int, comment_id: int) -> None:
    """Удаляет комментарий задачи."""
    with get_session() as session:
        stmt = delete(TaskComment).where(
            TaskComment.card_id == card_id,
            TaskComment.comment_id == comment_id
        )
        session.execute(stmt)


def get_task_comments(card_id: int) -> Set[int]:
    """Возвращает set comment_id комментариев задачи."""
    with get_session() as session:
        stmt = select(TaskComment.comment_id).where(TaskComment.card_id == card_id)
        result = session.execute(stmt).scalars().all()
        return set(result)


def delete_task_full(card_id: int) -> None:
    """
    Полностью удаляет карточку и все связанные записи из БД.
    Используется после архивации на стороне Nextcloud.
    """
    with get_session() as session:
        # Удаляем связанные записи
        session.execute(delete(DeadlineReminder).where(DeadlineReminder.card_id == card_id))
        session.execute(delete(TaskLabel).where(TaskLabel.card_id == card_id))
        session.execute(delete(TaskComment).where(TaskComment.card_id == card_id))
        session.execute(delete(TaskAttachment).where(TaskAttachment.card_id == card_id))
        session.execute(delete(TaskAssignee).where(TaskAssignee.card_id == card_id))
        session.execute(delete(TaskStat).where(TaskStat.card_id == card_id))
        session.execute(delete(Task).where(Task.card_id == card_id))


def get_etag_count(card_id: int) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Возвращает (etag, comments_count, attachments_count) для задачи."""
    with get_session() as session:
        task = session.get(Task, card_id)
        if not task:
            return None, None, None

        stat = session.get(TaskStat, card_id)
        if stat:
            return task.etag, stat.comments_count, stat.attachments_count
        return task.etag, None, None
