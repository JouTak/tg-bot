from typing import Optional, Dict, List, Tuple

from sqlalchemy import select, delete

from source.db.db import get_session
from source.migrations.models import User


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
    with get_session() as session:
        stmt = select(User).where(User.nc_email == email)
        user = session.execute(stmt).scalar_one_or_none()
        return user.tg_id if user else None


def get_user_credentials_from_db(email: str) -> Optional[Tuple[str, str]]:
    """Возвращает (nc_login, nc_token) по email."""
    with get_session() as session:
        stmt = select(User).where(User.nc_email == email)
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


def save_login_to_db_with_token(tg_id: int, nc_login: str, email: str, nc_token: str) -> None:
    """Сохраняет или обновляет пользователя с токеном."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user:
            user.nc_login = nc_login
            user.nc_email = email
            user.nc_token = nc_token
        else:
            user = User(tg_id=tg_id, nc_login=nc_login, nc_email=email, nc_token=nc_token)
            session.add(user)


def save_email_by_username(nc_email: str, nc_login: str) -> None:
    """Обновляет email пользователя по логину."""
    with get_session() as session:
        stmt = select(User).where(User.nc_login == nc_login)
        user = session.execute(stmt).scalar_one_or_none()
        if user:
            user.nc_email = nc_email


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
