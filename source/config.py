import os
from dotenv import load_dotenv
import subprocess

load_dotenv()

missing = [k for k in (
    "BOT_TOKEN", "BASE_URL", "NEXTCLOUD_USER", "NEXTCLOUD_PASS",
    "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB") if not os.getenv(k)]
if missing:
    raise RuntimeError(", ".join(missing))


def _detect_commit() -> str:
    """
    Определяет хеш коммита:
    1. Из переменной окружения GIT_COMMIT (CI/Docker)
    2. Из git rev-parse --short HEAD (локальный запуск)
    3. 'unknown' если ничего не доступно
    """
    env_val = os.getenv("GIT_COMMIT", "").strip()
    if env_val and env_val != "unknown":
        return env_val
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


COMMIT_HASH = _detect_commit()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")

USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")

FORUM_CHAT_ID = int(os.getenv("FORUM_CHAT_ID", "0"))

BOT_LOG_TOPIC_ID_RAW = os.getenv("BOT_LOG_TOPIC_ID", "0")
BOT_LOG_TOPIC_ID = None if BOT_LOG_TOPIC_ID_RAW in ("None", "", None) else (int(BOT_LOG_TOPIC_ID_RAW) or None)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASS = os.getenv("MYSQL_PASS")
MYSQL_DB = os.getenv("MYSQL_DB")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
DEADLINES_INTERVAL = int(os.getenv("DEADLINES_INTERVAL", "2"))
QUIET_HOURS = os.getenv("QUIET_HOURS", "0-8")
DEADLINE_REPEAT_DAYS = int(os.getenv("DEADLINE_REPEAT_DAYS", "5"))
ARCHIVE_AFTER_DAYS = int(os.getenv("ARCHIVE_AFTER_DAYS", "7"))
TIMEZONE = "Europe/Moscow"

APP_DEBUG = os.getenv("APP_DEBUG", "0")

HEADERS = {'OCS-APIRequest': 'true', 'Content-Type': 'application/json'}

EXCLUDED_CARD_IDS = {int(i) for i in os.getenv("EXCLUDED_CARD_IDS", "").split(",") if i and i.isdigit()}
