import os
import logging
from logging import FileHandler, StreamHandler, Formatter

from source.config import APP_DEBUG

logger = logging.getLogger("source")
_APP_DEBUG = APP_DEBUG=="1"

def is_debug() -> bool:
    return _APP_DEBUG

def setup_logging():
    if logger.handlers:
        return logger

    level = logging.DEBUG if _APP_DEBUG else logging.INFO
    fmt = Formatter('[%(levelname)s] %(asctime)s - %(message)s')

    sh = StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)

    fh = FileHandler("bot.log", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    logger.setLevel(level)
    logger.addHandler(sh)
    logger.addHandler(fh)
    logger.propagate = False

    # приглушаем низкоуровневые сетевые логи
    for name in ["urllib3", "requests", "httpx", "httpcore"]:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("telebot").setLevel(logging.INFO if _APP_DEBUG else logging.WARNING)
    return logger
