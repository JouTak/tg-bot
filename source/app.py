import threading
from source.app_logging import logger, is_debug
from source.scheduler import poll_new_tasks
from source.connections.bot_factory import bot
import source.handlers  # noqa: F401
import source.callbacks  # noqa: F401

def _get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        try:
            return obj.get(name, default)
        except Exception:
            return default

def _updates_listener(updates):
    # включается только при дебаге
    for u in updates:
        cq = getattr(u, "callback_query", None)
        msg = getattr(u, "message", None)
        if cq and getattr(cq, "message", None):
            logger.info(f"[UPD] callback_query chat_id={cq.message.chat.id} data={cq.data!r}")
        elif msg:
            logger.info(f"[UPD] message chat_id={msg.chat.id} type={msg.chat.type} text={getattr(msg,'text',None)!r}")

def run():
    if is_debug():
        try:
            info = bot.get_webhook_info()
            logger.debug(f"Webhook(before): url='{_get(info,'url','')}' pending={_get(info,'pending_update_count',0)}")
        except Exception as e:
            logger.debug(f"Webhook info error: {e}")

    try:
        bot.remove_webhook(drop_pending_updates=True)
    except TypeError:
        bot.remove_webhook()

    threading.Thread(target=poll_new_tasks, daemon=True).start()

    if is_debug():
        bot.set_update_listener(_updates_listener)

    me = bot.get_me()
    logger.info(f"Запускается polling Telegram как @{me.username} (id={me.id})")
    bot.infinity_polling(skip_pending=True)
