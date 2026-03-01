from source.db.db import Base

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text,
    DateTime, TIMESTAMP, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    tg_id = Column(BigInteger, primary_key=True)
    nc_login = Column(String(100), nullable=False)

class Task(Base):
    __tablename__ = "tasks"

    card_id = Column(Integer, primary_key=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    board_id = Column(Integer, nullable=False)
    board_title = Column(String(100), nullable=False)

    stack_id = Column(Integer, nullable=False)
    stack_title = Column(String(100), nullable=False)

    duedate = Column(DateTime, nullable=True)

    created_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp()
    )

    etag = Column(String(255), nullable=True)

    prev_stack_id = Column(Integer, nullable=True)
    prev_stack_title = Column(String(100), nullable=True)

    next_stack_id = Column(Integer, nullable=True)
    next_stack_title = Column(String(100), nullable=True)

    done = Column(TIMESTAMP, nullable=True)

    # Relationships
    assignees = relationship("TaskAssignee", back_populates="task", cascade="all, delete-orphan")
    stats = relationship("TaskStat", back_populates="task", uselist=False, cascade="all, delete-orphan")
    labels = relationship("TaskLabel", back_populates="task", cascade="all, delete-orphan")
    reminders = relationship("DeadlineReminder", back_populates="task", cascade="all, delete-orphan")

class TaskAssignee(Base):
    __tablename__ = "task_assignees"

    card_id = Column(Integer, ForeignKey("tasks.card_id"), primary_key=True)
    nc_login = Column(String(100), primary_key=True)

    task = relationship("Task", back_populates="assignees")

class TaskStat(Base):
    __tablename__ = "task_stats"

    card_id = Column(Integer, ForeignKey("tasks.card_id"), primary_key=True)

    comments_count = Column(Integer, nullable=False, default=0)
    attachments_count = Column(Integer, nullable=False, default=0)

    task = relationship("Task", back_populates="stats")


class DeadlineReminder(Base):
    __tablename__ = "deadline_reminders"

    card_id = Column(Integer, ForeignKey("tasks.card_id"), primary_key=True)
    login = Column(String(100), primary_key=True)
    stage = Column(String(32), primary_key=True)

    sent_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp()
    )

    task = relationship("Task", back_populates="reminders")

class BoardLogTopic(Base):
    __tablename__ = "board_log_topics"

    board_id = Column(Integer, primary_key=True)
    message_thread_id = Column(BigInteger, nullable=False)

    created_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp()
    )

class TaskLabel(Base):
    __tablename__ = "task_labels"

    card_id = Column(Integer, ForeignKey("tasks.card_id"), primary_key=True)
    label = Column(String(100), primary_key=True)

    task = relationship("Task", back_populates="labels")
