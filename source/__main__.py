from source.app_logging import setup_logging, logger
from source.app import run
from source.config import COMMIT_HASH

if __name__ == "__main__":
    setup_logging()
    logger.info(f"""
---Бот запускается---
Разработка: https://github.com/JouTak/tg-bot.git
Актуальный коммит: {COMMIT_HASH}
""")
    run()
