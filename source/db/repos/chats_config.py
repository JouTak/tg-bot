from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select

from source.db.db import get_session
from source.migrations.models import ChatConfig


def _as_dict(config: ChatConfig) -> Dict[str, Any]:
    return {
        "id": config.id,
        "chat_id": int(config.chat_id),
        "enabled": bool(config.enabled),
        "mode": config.mode,
        "target_board_id": config.target_board_id,
        "tags": deepcopy(config.tags or {}),
        "board_blacklist": list(config.board_blacklist or []),
        "meta": deepcopy(config.meta or {}),
    }


def get_chat_config(chat_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        config = session.execute(
            select(ChatConfig).where(ChatConfig.chat_id == int(chat_id))
        ).scalar_one_or_none()
        return _as_dict(config) if config else None


def get_enabled_chat_configs() -> List[Dict[str, Any]]:
    with get_session() as session:
        configs = session.execute(
            select(ChatConfig).where(ChatConfig.enabled.is_(True))
        ).scalars().all()
        return [_as_dict(config) for config in configs]


def create_chat_config(
    chat_id: int,
    mode: str = "boards",
    *,
    enabled: bool = True,
    target_board_id: Optional[int] = None,
    tags: Optional[Dict[str, int]] = None,
    board_blacklist: Optional[Iterable[int]] = None,
    known_tag_ids: Optional[Iterable[int]] = None,
    default_topic_id: Optional[int] = None,
    target_board_ids: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    if mode not in {"boards", "tags"}:
        raise ValueError("mode должен быть 'boards' или 'tags'")
    meta = {}
    if known_tag_ids is not None:
        meta["known_tag_ids"] = sorted({int(tag_id) for tag_id in known_tag_ids})
    if default_topic_id is not None:
        meta["default_topic_id"] = int(default_topic_id)
    if target_board_ids is not None:
        meta["target_board_ids"] = sorted({int(board_id) for board_id in target_board_ids})

    with get_session() as session:
        config = session.execute(
            select(ChatConfig).where(ChatConfig.chat_id == int(chat_id))
        ).scalar_one_or_none()
        if config is None:
            config = ChatConfig(chat_id=int(chat_id))
            session.add(config)
        config.enabled = bool(enabled)
        config.mode = mode
        config.target_board_id = target_board_id
        config.tags = {str(k): int(v) for k, v in (tags or {}).items()}
        config.board_blacklist = sorted({int(v) for v in (board_blacklist or [])})
        config.meta = meta
    return get_chat_config(chat_id)


def update_chat_config(chat_id: int, **values: Any) -> Optional[Dict[str, Any]]:
    allowed = {"enabled", "mode", "target_board_id", "tags", "board_blacklist", "meta"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Неизвестные поля конфигурации: {', '.join(sorted(unknown))}")
    if "mode" in values and values["mode"] not in {"boards", "tags"}:
        raise ValueError("mode должен быть 'boards' или 'tags'")
    with get_session() as session:
        config = session.execute(
            select(ChatConfig).where(ChatConfig.chat_id == int(chat_id))
        ).scalar_one_or_none()
        if config is None:
            return None
        for key, value in values.items():
            if key == "tags":
                value = {str(k): int(v) for k, v in (value or {}).items()}
            elif key == "board_blacklist":
                value = sorted({int(v) for v in (value or [])})
            elif key == "meta":
                value = deepcopy(value or {})
            setattr(config, key, value)
    return get_chat_config(chat_id)


def delete_chat_config(chat_id: int) -> bool:
    with get_session() as session:
        config = session.execute(
            select(ChatConfig).where(ChatConfig.chat_id == int(chat_id))
        ).scalar_one_or_none()
        if config is None:
            return False
        session.delete(config)
        return True


def set_chat_enabled(chat_id: int, enabled: bool) -> bool:
    return update_chat_config(chat_id, enabled=enabled) is not None


def set_chat_mode(chat_id: int, mode: str) -> bool:
    return update_chat_config(chat_id, mode=mode) is not None


def set_target_board(chat_id: int, board_id: Optional[int]) -> bool:
    return update_chat_config(chat_id, target_board_id=board_id) is not None


def set_target_boards(chat_id: int, board_ids: Iterable[int]) -> bool:
    """Задаёт одну или несколько (обычно не более двух) досок для режима tags."""
    config = get_chat_config(chat_id)
    if config is None:
        return False
    meta = config["meta"]
    meta["target_board_ids"] = sorted({int(board_id) for board_id in board_ids})
    ids = meta["target_board_ids"]
    return update_chat_config(
        chat_id,
        target_board_id=ids[0] if len(ids) == 1 else None,
        meta=meta,
    ) is not None


def set_default_topic(chat_id: int, topic_id: Optional[int]) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    meta = config["meta"]
    if topic_id is None:
        meta.pop("default_topic_id", None)
    else:
        meta["default_topic_id"] = int(topic_id)
    return update_chat_config(chat_id, meta=meta) is not None


def set_board_topic(chat_id: int, board_id: int, topic_id: int) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    meta = config["meta"]
    board_topics = meta.setdefault("board_topics", {})
    board_topics[str(int(board_id))] = int(topic_id)
    return update_chat_config(chat_id, meta=meta) is not None


def set_tag_topic(chat_id: int, tag_id: int, topic_id: int) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    tags = config["tags"]
    tags[str(int(tag_id))] = int(topic_id)
    return update_chat_config(chat_id, tags=tags) is not None


def remove_tag_topic(chat_id: int, tag_id: int) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    tags = config["tags"]
    tags.pop(str(int(tag_id)), None)
    return update_chat_config(chat_id, tags=tags) is not None


def set_board_blacklist(chat_id: int, board_ids: Iterable[int]) -> bool:
    return update_chat_config(chat_id, board_blacklist=list(board_ids)) is not None


def add_board_to_blacklist(chat_id: int, board_id: int) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    blocked = set(config["board_blacklist"])
    blocked.add(int(board_id))
    return set_board_blacklist(chat_id, blocked)


def remove_board_from_blacklist(chat_id: int, board_id: int) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    blocked = set(config["board_blacklist"])
    blocked.discard(int(board_id))
    return set_board_blacklist(chat_id, blocked)


def set_known_tag_ids(chat_id: int, tag_ids: Iterable[int]) -> bool:
    config = get_chat_config(chat_id)
    if config is None:
        return False
    meta = config["meta"]
    meta["known_tag_ids"] = sorted({int(tag_id) for tag_id in tag_ids})
    return update_chat_config(chat_id, meta=meta) is not None


def initialize_known_tags_from_db(chat_id: int) -> bool:
    """Фиксирует текущий набор ID меток из задач БД как известный для беседы."""
    from source.db.repos.tasks import get_all_tag_ids
    return set_known_tag_ids(chat_id, get_all_tag_ids())


def _resolve_topic(config: Dict[str, Any], board_id: int, tag_ids: Iterable[int], board_topic: Optional[int]):
    """Возвращает (разрешено, topic_id, причина)."""
    if int(board_id) in {int(v) for v in config["board_blacklist"]}:
        return False, None, "board_blacklisted"

    if config["mode"] == "boards":
        known_values = config["meta"].get("known_tag_ids")
        if known_values is not None:
            known = {int(v) for v in known_values}
            if any(int(tag_id) not in known for tag_id in tag_ids):
                return False, None, "unknown_tag"
        default_topic = config["meta"].get("default_topic_id")
        return True, board_topic if board_topic is not None else default_topic, "boards"

    if config["mode"] == "tags":
        target_boards = config["meta"].get("target_board_ids")
        if target_boards is None:
            target_boards = [config["target_board_id"]] if config["target_board_id"] is not None else []
        if int(board_id) not in {int(v) for v in target_boards}:
            return False, None, "wrong_board"
        mapping = config["tags"]
        for tag_id in tag_ids:
            topic_id = mapping.get(str(int(tag_id)))
            if topic_id is not None:
                return True, int(topic_id), "mapped_tag"
        return True, config["meta"].get("default_topic_id"), "unmapped_tag"

    return False, None, "invalid_mode"


def resolve_task_chats(board_id: int, tag_ids: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    """Список получателей и topic_id для конкретной карточки."""
    from source.config import BOT_LOG_TOPIC_ID, FORUM_CHAT_ID
    from source.db.repos.boards import get_message_thread_id

    tags = [int(v) for v in (tag_ids or [])]
    result = []
    for config in get_enabled_chat_configs():
        board_topic = None
        if config["mode"] == "boards":
            if int(config["chat_id"]) == int(FORUM_CHAT_ID):
                board_topic = get_message_thread_id(board_id)
            else:
                board_topic = (config["meta"].get("board_topics") or {}).get(str(int(board_id)))
        allowed, topic_id, reason = _resolve_topic(config, board_id, tags, board_topic)
        if not allowed:
            continue
        if topic_id is None and int(config["chat_id"]) == int(FORUM_CHAT_ID):
            topic_id = BOT_LOG_TOPIC_ID
        result.append({"chat_id": config["chat_id"], "topic_id": topic_id, "reason": reason})
    return result
