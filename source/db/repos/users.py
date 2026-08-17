from datetime import timezone
from typing import Optional, Dict, List, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, delete, func

from source.config import TIMEZONE
from source.db.db import get_session
from source.migrations.models import User


NEXTCLOUD_FIELD_MISSING = object()


def normalize_tzid(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    tzid = value.strip()
    if not tzid:
        return None
    try:
        ZoneInfo(tzid)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return None
    return tzid


def _normalize_email(value: object):
    if value is None:
        return None
    if not isinstance(value, str):
        return NEXTCLOUD_FIELD_MISSING
    return value.strip().lower() or None


def get_login_by_tg_id(tg_id: int) -> Optional[str]:
    """Возвращает Nextcloud-логин пользователя по Telegram ID."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_login if user else None


def get_email_by_tg_id(tg_id: int) -> Optional[str]:
    """Возвращает email пользователя по Telegram ID."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_email if user else None


def get_tg_id_by_email(email: str) -> Optional[int]:
    """Возвращает Telegram ID по email."""
    normalized = _normalize_email(email)
    if normalized in (None, NEXTCLOUD_FIELD_MISSING):
        return None
    with get_session() as session:
        stmt = select(User).where(func.lower(func.trim(User.nc_email)) == normalized)
        user = session.execute(stmt).scalar_one_or_none()
        return user.tg_id if user else None


def get_user_credentials_from_db(email: str) -> Optional[Tuple[str, str]]:
    """Возвращает (nc_login, nc_token) по email."""
    normalized = _normalize_email(email)
    if normalized in (None, NEXTCLOUD_FIELD_MISSING):
        return None
    with get_session() as session:
        stmt = select(User).where(func.lower(func.trim(User.nc_email)) == normalized)
        user = session.execute(stmt).scalar_one_or_none()
        return (user.nc_login, user.nc_token) if user else None


def save_login_to_db(tg_id: int, nc_login: str) -> None:
    """Сохраняет или обновляет соответствие Telegram ID и Nextcloud логина."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user:
            user.nc_login = nc_login
        else:
            user = User(tg_id=tg_id, nc_login=nc_login)
            session.add(user)


def save_login_to_db_with_token(
        tg_id: int, nc_login: str, email: object, nc_token: str,
        timezone_value: object = NEXTCLOUD_FIELD_MISSING) -> None:
    """Сохраняет или обновляет пользователя с токеном."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if not user:
            user = User(tg_id=tg_id, nc_login=nc_login)
            session.add(user)
        user.nc_login = nc_login
        normalized_email = _normalize_email(email)
        if normalized_email is not NEXTCLOUD_FIELD_MISSING:
            user.nc_email = normalized_email
        user.nc_token = nc_token
        _apply_nextcloud_timezone(user, timezone_value)
        from source.migrations.models import NextCloudLogin
        session.execute(delete(NextCloudLogin).where(NextCloudLogin.tg_id == tg_id))


def _apply_nextcloud_timezone(user: User, value: object) -> None:
    if value is NEXTCLOUD_FIELD_MISSING:
        return
    normalized = normalize_tzid(value)
    if normalized:
        user.nc_timezone = normalized
    elif value is None or (isinstance(value, str) and not value.strip()):
        user.nc_timezone = None


def update_nextcloud_profile(
        nc_login: str, *, email: object = NEXTCLOUD_FIELD_MISSING,
        timezone_value: object = NEXTCLOUD_FIELD_MISSING) -> bool:
    """Обновляет поля профиля, сохраняя отсутствующие и очищая явно пустые."""
    with get_session() as session:
        stmt = select(User).where(User.nc_login == nc_login)
        user = session.execute(stmt).scalar_one_or_none()
        if not user:
            return False
        normalized_email = _normalize_email(email)
        if normalized_email is not NEXTCLOUD_FIELD_MISSING:
            user.nc_email = normalized_email
        _apply_nextcloud_timezone(user, timezone_value)
        return True


def save_email_by_username(nc_email: str, nc_login: str) -> None:
    """Обновляет email пользователя по логину."""
    update_nextcloud_profile(nc_login, email=nc_email)


def save_timezone(tg_id: int, timezone_name: str) -> None:
    """Сохраняет локальный IANA timezone override."""
    normalized = normalize_tzid(timezone_name)
    if not normalized:
        raise ValueError("Unknown IANA timezone")
    with get_session() as session:
        user = session.get(User, tg_id)
        if not user:
            raise LookupError(tg_id)
        user.timezone_override = normalized


def clear_timezone_override(tg_id: int) -> None:
    with get_session() as session:
        user = session.get(User, tg_id)
        if not user:
            raise LookupError(tg_id)
        user.timezone_override = None


def get_timezone(tg_id: Optional[int]):
    """Возвращает effective timezone: override -> Nextcloud -> default -> UTC."""
    candidates = []
    if tg_id is not None:
        with get_session() as session:
            user = session.get(User, tg_id)
            if user:
                candidates.extend((user.timezone_override, user.nc_timezone))
    candidates.append(TIMEZONE)
    for candidate in candidates:
        normalized = normalize_tzid(candidate)
        if normalized:
            return ZoneInfo(normalized)
    return timezone.utc


def get_user_list() -> List[Tuple[int, str]]:
    """Возвращает список всех пользователей в формате [(tg_id, nc_login)]."""
    with get_session() as session:
        stmt = select(User.tg_id, User.nc_login)
        result = session.execute(stmt).all()
        return [(row.tg_id, row.nc_login) for row in result]


def get_user_map() -> Dict[str, int]:
    """
    Возвращает словарь { nc_login: tg_id }.
    Используется для отправки уведомлений назначенным пользователям.
    """
    with get_session() as session:
        stmt = select(User.tg_id, User.nc_login)
        result = session.execute(stmt).all()
        return {row.nc_login: row.tg_id for row in result}


def get_users() -> List[Dict[str, str]]:
    """
    Возвращает список словарей { username: nc_login, password: nc_token }.
    """
    with get_session() as session:
        stmt = select(User.nc_login, User.nc_token)
        result = session.execute(stmt).all()
        return [{"username": row.nc_login, "password": row.nc_token} for row in result]


def save_login_token(tg_id: int, token: str) -> None:
    """Сохраняет временный токен авторизации."""
    from source.migrations.models import NextCloudLogin
    with get_session() as session:
        login_token = NextCloudLogin(tg_id=tg_id, token=token)
        session.add(login_token)


def delete_login_token(tg_id: int) -> None:
    """Удаляет временный токен авторизации."""
    from source.migrations.models import NextCloudLogin
    with get_session() as session:
        stmt = delete(NextCloudLogin).where(NextCloudLogin.tg_id == tg_id)
        session.execute(stmt)


def get_token(tg_id: int) -> Optional[str]:
    """Возвращает временный токен авторизации."""
    from source.migrations.models import NextCloudLogin
    with get_session() as session:
        login_token = session.get(NextCloudLogin, tg_id)
        return login_token.token if login_token else None


def get_nc_token(tg_id: int) -> Optional[str]:
    """Возвращает Nextcloud-токен пользователя."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_token if user else None
