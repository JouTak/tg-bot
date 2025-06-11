import os
import logging
import threading
import time
import telebot
import requests
import mysql.connector
from requests.auth import HTTPBasicAuth
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN      = os.getenv("BOT_TOKEN")
BASE_URL       = os.getenv("BASE_URL")
USERNAME       = os.getenv("NEXTCLOUD_USER")
PASSWORD       = os.getenv("NEXTCLOUD_PASS")

MYSQL_HOST     = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER     = os.getenv("MYSQL_USER")
MYSQL_PASS     = os.getenv("MYSQL_PASS")
MYSQL_DB       = os.getenv("MYSQL_DB")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

missing = [k for k in (
    "BOT_TOKEN","BASE_URL","NEXTCLOUD_USER","NEXTCLOUD_PASS",
    "MYSQL_USER","MYSQL_PASS","MYSQL_DB") if not os.getenv(k)]
if missing:
    raise RuntimeError(f"Не заданы переменные окружения: {', '.join(missing)}")

HEADERS = {'OCS-APIRequest': 'true', 'Content-Type': 'application/json'}

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_mysql_connection():
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        charset="utf8mb4"
    )
    return conn

def get_login_by_tg_id(tg_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_login FROM users WHERE tg_id = %s", (tg_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None

def save_login_to_db(tg_id, nc_login):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (tg_id, nc_login) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE nc_login = VALUES(nc_login)",
        (tg_id, nc_login)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_user_list():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, nc_login FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [(row[0], row[1]) for row in rows]

def get_tasks_from_db(tg_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT card_id FROM tasks WHERE tg_id = %s", (tg_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(r[0] for r in rows)

def save_task_to_db(tg_id, card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO tasks
          (tg_id, card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            tg_id,
            card_id,
            title,
            description,
            board_id,
            board_title,
            stack_id,
            stack_title,
            duedate
        )
    )
    conn.commit()
    cursor.close()
    conn.close()

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Введите свой логин Nextcloud:")

@bot.message_handler(commands=['mycards'])
def show_user_cards(message):
    chat_id = message.chat.id
    saved_login = get_login_by_tg_id(chat_id)
    if not saved_login:
        bot.send_message(chat_id, "Сначала отправьте логин командой /start.")
        return
    login = saved_login
    bot.send_message(chat_id, "Ищу задачи...")
    tasks = fetch_user_tasks(login)
    for t in tasks:
        save_task_to_db(
            chat_id,
            t['card_id'],
            t['title'],
            t['description'],
            t['board_id'],
            t['board_title'],
            t['stack_id'],
            t['stack_title'],
            t['duedate']
        )
        kb = InlineKeyboardMarkup()
        if t['prev_stack_id'] is not None:
            kb.add(InlineKeyboardButton(
                text=f"⬅ {t['prev_stack_title']}",
                callback_data=f"move:{t['board_id']}:{t['stack_id']}:{t['card_id']}:{t['prev_stack_id']}"
            ))
        if t['next_stack_id'] is not None:
            kb.add(InlineKeyboardButton(
                text=f"➡ {t['next_stack_title']}",
                callback_data=f"move:{t['board_id']}:{t['stack_id']}:{t['card_id']}:{t['next_stack_id']}"
            ))
        msg = (
            f"{t['title']}\n"
            f"Board: {t['board_title']}\n"
            f"Column: {t['stack_title']}\n"
            f"Due: {t['duedate'] or '—'}\n"
            f"{t['description'] or '—'}"
        )
        bot.send_message(chat_id, msg, reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: get_login_by_tg_id(msg.chat.id) is None)
def save_login(message):
    chat_id = message.chat.id
    nc_login = message.text.strip()
    save_login_to_db(chat_id, nc_login)
    bot.send_message(chat_id, f"Логин `{nc_login}` сохранён.", parse_mode="Markdown")

def fetch_user_tasks(login):
    result = []
    boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    boards_resp.raise_for_status()
    boards = boards_resp.json()
    for board in boards:
        if board.get('archived', True):
            continue
        board_id = board['id']
        board_title = board['title']
        stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
        stacks_resp.raise_for_status()
        stacks = sorted(stacks_resp.json(), key=lambda s: s['order'])
        for idx, stack in enumerate(stacks):
            stack_id = stack['id']
            stack_title = stack['title']
            cards = stack.get('cards') or []
            if not cards:
                stack_data = requests.get(f"{BASE_URL}/boards/{board_id}/stacks/{stack_id}?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
                stack_data.raise_for_status()
                cards = stack_data.json().get('cards', [])
            for card in cards:
                assigned = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                if login in assigned:
                    prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                    prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                    next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                    next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None
                    duedate_iso = card.get('duedate')
                    duedate_dt = datetime.fromisoformat(duedate_iso) if duedate_iso else None
                    result.append({
                        'card_id': card['id'],
                        'title': card['title'],
                        'description': card.get('description', ''),
                        'board_id': board_id,
                        'board_title': board_title,
                        'stack_id': stack_id,
                        'stack_title': stack_title,
                        'prev_stack_id': prev_stack_id,
                        'prev_stack_title': prev_stack_title,
                        'next_stack_id': next_stack_id,
                        'next_stack_title': next_stack_title,
                        'duedate': duedate_dt
                    })
    return result

@bot.callback_query_handler(func=lambda call: call.data.startswith("move:"))
def handle_card_move(call):
    _, board_id, current_stack_id, card_id, new_stack_id = call.data.split(":")
    board_id = int(board_id)
    current_stack_id = int(current_stack_id)
    card_id = int(card_id)
    new_stack_id = int(new_stack_id)
    all_stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    all_stacks_resp.raise_for_status()
    all_stacks = sorted(all_stacks_resp.json(), key=lambda s: s['order'])
    new_stack_data = next(s for s in all_stacks if s['id'] == new_stack_id)
    position = len(new_stack_data.get("cards", []))
    reorder_url = f"{BASE_URL}/boards/{board_id}/stacks/{new_stack_id}/cards/{card_id}/reorder"
    payload = {"stackId": new_stack_id, "order": position}
    move_resp = requests.put(reorder_url, headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD), json=payload)
    if move_resp.status_code not in (200, 204):
        bot.answer_callback_query(call.id, f"Ошибка API ({move_resp.status_code})")
        return
    updated_stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    updated_stacks_resp.raise_for_status()
    updated_stacks = sorted(updated_stacks_resp.json(), key=lambda s: s['order'])
    new_idx = next(idx for idx, s in enumerate(updated_stacks) if s['id'] == new_stack_id)
    new_kb = InlineKeyboardMarkup()
    if new_idx > 0:
        prev_stack = updated_stacks[new_idx - 1]
        new_kb.add(InlineKeyboardButton(
            text=f"⬅ {prev_stack['title']}",
            callback_data=f"move:{board_id}:{new_stack_id}:{card_id}:{prev_stack['id']}"
        ))
    if new_idx < len(updated_stacks) - 1:
        next_stack = updated_stacks[new_idx + 1]
        new_kb.add(InlineKeyboardButton(
            text=f"➡ {next_stack['title']}",
            callback_data=f"move:{board_id}:{new_stack_id}:{card_id}:{next_stack['id']}"
        ))
    bot.answer_callback_query(call.id, "Перемещено")
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=new_kb)

def poll_new_tasks():
    while True:
        users = get_user_list()
        for tg_id, login in users:
            existing = get_tasks_from_db(tg_id)
            current = fetch_user_tasks(login)
            current_ids = set(item['card_id'] for item in current)
            new_ids = current_ids - existing
            for item in current:
                if item['card_id'] in new_ids:
                    save_task_to_db(
                        tg_id,
                        item['card_id'],
                        item['title'],
                        item['description'],
                        item['board_id'],
                        item['board_title'],
                        item['stack_id'],
                        item['stack_title'],
                        item['duedate']
                    )
                    kb = InlineKeyboardMarkup()
                    if item['prev_stack_id'] is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"⬅ {item['prev_stack_title']}",
                            callback_data=(
                                f"move:{item['board_id']}:"
                                f"{item['stack_id']}:"
                                f"{item['card_id']}:"
                                f"{item['prev_stack_id']}"
                            )
                        ))
                    if item['next_stack_id'] is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"➡ {item['next_stack_title']}",
                            callback_data=(
                                f"move:{item['board_id']}:"
                                f"{item['stack_id']}:"
                                f"{item['card_id']}:"
                                f"{item['next_stack_id']}"
                            )
                        ))
                    msg = (
                        f"Новая задача: {item['title']}\n"
                        f"Board: {item['board_title']}\n"
                        f"Column: {item['stack_title']}\n"
                        f"Due: {item['duedate'] or '—'}\n"
                        f"{item['description'] or '—'}"
                    )
                    bot.send_message(tg_id, msg, reply_markup=kb, parse_mode="Markdown")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    t = threading.Thread(target=poll_new_tasks, daemon=True)
    t.start()
    bot.polling()
