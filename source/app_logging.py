import os
import logging
import shutil
from logging import FileHandler, StreamHandler, Formatter

from source.config import APP_DEBUG, BUFF_SIZE

logger = logging.getLogger("source")
_APP_DEBUG = APP_DEBUG == "1"

class TrimFileHandler(FileHandler):
    def __init__(self, filename, max_bytes, check_every=1000, **kwargs):
        super().__init__(filename, **kwargs)
        self.max_bytes = max_bytes
        self.check_every = check_every
        self.counter = 0

    def emit(self, record):
        self.counter += 1

        if self.counter >= self.check_every:
            self.counter = 0
            self._trim_if_needed()

        super().emit(record)

    def _trim_if_needed(self):
        size = os.path.getsize(self.baseFilename)
        if size <= self.max_bytes:
            return

        self.stream.close()

        tmp = self.baseFilename + ".tmp"

        with open(self.baseFilename, "rb") as src:
            src.seek(size - self.max_bytes // 2)

            src.readline()

            with open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)

        os.replace(tmp, self.baseFilename)
        self.stream = self._open()


def is_debug() -> bool:
    """
    Возвращает True, если приложение запущено в режиме отладки (APP_DEBUG=1).
    """
    return _APP_DEBUG


def setup_logging():
    """
    Настраивает логирование:
    - вывод в консоль
    - запись в файл bot.log
    - уровень DEBUG или INFO
    - отключает шумные логи библиотек requests/urllib3
    """
    if logger.handlers:
        return logger

    level = logging.DEBUG if _APP_DEBUG else logging.INFO
    fmt = Formatter('[%(levelname)s] %(asctime)s - %(message)s')

    sh = StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)

    if not os.path.exists('logs/'):
        os.makedirs('logs/')

    fh = TrimFileHandler(
        "logs/bot.log",
        max_bytes=BUFF_SIZE * 1024 * 1024,
        check_every=1000,
        encoding="utf-8",
    )
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
