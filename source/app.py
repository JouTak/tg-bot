import socket
import http.client
import threading
import time

from source.app_logging import logger, is_debug
from source.scheduler import poll_new_tasks
from source.connections.bot_factory import bot
from source.connections.sender import send_message_limited
from source.config import FORUM_CHAT_ID, BOT_LOG_TOPIC_ID, COMMIT_HASH
import source.handlers  # noqa: F401
import source.callbacks  # noqa: F401
from source.deadlines import poll_deadlines


def _get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        try:
            return obj.get(name, default)
        except Exception:
            return default


def _updates_listener(updates):
    for u in updates:
        cq = getattr(u, "callback_query", None)
        msg = getattr(u, "message", None)
        if cq and getattr(cq, "message", None):
            logger.info(f"[UPD] callback_query chat_id={cq.message.chat.id} data={cq.data!r}")
        elif msg:
            logger.info(f"[UPD] message chat_id={msg.chat.id} type={msg.chat.type} text={getattr(msg, 'text', None)!r}")


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{int(round(seconds * 1000))} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m {s}s"


def _is_network_error(exc: BaseException) -> bool:
    from requests.exceptions import ConnectionError, Timeout
    if isinstance(exc, (ConnectionError, Timeout)):
        return True
    cur = exc
    while cur:
        if isinstance(cur, (
                ConnectionError, Timeout,
                socket.gaierror,
                ConnectionAbortedError,
                ConnectionResetError,
                http.client.RemoteDisconnected,
        )):
            return True
        name = cur.__class__.__name__
        if name in {
            "NameResolutionError", "NewConnectionError",
            "MaxRetryError", "ProtocolError",
        }:
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False


def _brief(exc: BaseException) -> str:
    from requests.exceptions import ConnectionError, Timeout
    if isinstance(exc, Timeout):
        return "таймаут запроса"
    if isinstance(exc, ConnectionError):
        return "нет соединения"
    cur = exc
    while cur:
        if isinstance(cur, socket.gaierror):
            return "DNS недоступен"
        if isinstance(cur, http.client.RemoteDisconnected):
            return "удалённый сервер разорвал соединение"
        if isinstance(cur, ConnectionAbortedError):
            return "соединение прервано хостом"
        if isinstance(cur, ConnectionResetError):
            return "соединение сброшено"
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return exc.__class__.__name__


def _notify_startup():
    """
    Отправляет в форум-топик сообщение о запуске бота.
    - Если BOT_LOG_TOPIC_ID не задан — ничего не отправляет.
    - Если COMMIT_HASH известен — выводит коммит.
    - Иначе — сообщает о локальном билде.
    """
    if BOT_LOG_TOPIC_ID is None:
        return
    if COMMIT_HASH and COMMIT_HASH != "unknown":
        text = f"🔄 Бот перезапущен на коммите `{COMMIT_HASH}`!"
    else:
        text = "🔄 Бот перезапущен на локальном билде!"
    try:
        send_message_limited(
            FORUM_CHAT_ID,
            text,
            message_thread_id=BOT_LOG_TOPIC_ID,
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление о старте: {e}")


def run():
    if is_debug():
        try:
            info = bot.get_webhook_info()
            logger.debug(
                f"Webhook(before): url='{_get(info, 'url', '')}' pending={_get(info, 'pending_update_count', 0)}")
        except Exception as e:
            logger.debug(f"Webhook info error: {e}")

    try:
        bot.remove_webhook(drop_pending_updates=True)
    except TypeError:
        bot.remove_webhook()

    _notify_startup()

    threading.Thread(target=poll_new_tasks, daemon=True).start()
    threading.Thread(target=poll_deadlines, daemon=True).start()

    if is_debug():
        bot.set_update_listener(_updates_listener)

    backoff = 5.0
    while True:
        try:
            me = bot.get_me()
            logger.info(f"Запускается polling Telegram как @{me.username} (id={me.id})")
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=25)
            backoff = 5.0
        except Exception as e:
            if _is_network_error(e):
                logger.error(f"Нет связи с Telegram ({_brief(e)}). Повтор через {_fmt_duration(backoff)}.")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120.0)
            else:
                logger.exception("Сбой в polling; перезапуск через 5 секунд")
                time.sleep(5.0)
