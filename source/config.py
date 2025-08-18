import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")

USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")

FORUM_CHAT_ID = int(os.getenv("FORUM_CHAT_ID"))
BOT_LOG_TOPIC_ID = os.getenv("BOT_LOG_TOPIC_ID")
BOT_LOG_TOPIC_ID = None if BOT_LOG_TOPIC_ID == "None" else int(BOT_LOG_TOPIC_ID)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASS = os.getenv("MYSQL_PASS")
MYSQL_DB = os.getenv("MYSQL_DB")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
DEADLINES_INTERVAL=int(os.getenv("DEADLINES_INTERVAL", "2"))
QUIET_HOURS=os.getenv("QUIET_HOURS", "0-8")
TIMEZONE="Europe/Moscow"

APP_DEBUG = os.getenv("APP_DEBUG", "0")

missing = [k for k in (
    "BOT_TOKEN","BASE_URL","NEXTCLOUD_USER","NEXTCLOUD_PASS",
    "MYSQL_USER","MYSQL_PASS","MYSQL_DB") if not os.getenv(k)]
if missing:
    raise RuntimeError(", ".join(missing))

HEADERS = {'OCS-APIRequest': 'true', 'Content-Type': 'application/json'}
