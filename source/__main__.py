from source.app_logging import setup_logging, logger
from source.app import run

if __name__ == "__main__":
    setup_logging()
    logger.info("\n---Бот запускается---\nРазработка: https://github.com/JouTak/tg-bot.git\n")
    run()
