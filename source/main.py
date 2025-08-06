import os
import logging
import threading
import time
from collections import deque

import telebot
import requests
import mysql.connector
from requests.auth import HTTPBasicAuth
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN      = os.getenv("BOT_TOKEN")
BASE_URL       = os.getenv("BASE_URL")

USERNAME       = os.getenv("NEXTCLOUD_USER")
PASSWORD       = os.getenv("NEXTCLOUD_PASS")

FORUM_CHAT_ID = int(os.getenv("FORUM_CHAT_ID"))
BOT_LOG_TOPIC_ID = os.getenv("BOT_LOG_TOPIC_ID")
BOT_LOG_TOPIC_ID = None if BOT_LOG_TOPIC_ID == "None" else int(BOT_LOG_TOPIC_ID)

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

class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def wait(self):
        now = time.time()
        while self.calls and self.calls[0] <= now - self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                print("не справляюсь. ухожу в спячку")
                time.sleep(sleep_time)
                print("вышел из спячки")
        self.calls.append(time.time())

message_rate_limiter = RateLimiter(max_calls=20, period=60.0)

def send_message_limited(*args, **kwargs):
    message_rate_limiter.wait()
    return bot.send_message(*args, **kwargs)

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

def save_task_to_db(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks
          (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          title=VALUES(title),
          description=VALUES(description),
          board_id=VALUES(board_id),
          board_title=VALUES(board_title),
          stack_id=VALUES(stack_id),
          stack_title=VALUES(stack_title),
          duedate=VALUES(duedate)
        """,
        (
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
def save_task_basic(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks
          (card_id, title, description, board_id, board_title, stack_id, stack_title, duedate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          title=VALUES(title),
          description=VALUES(description),
          board_id=VALUES(board_id),
          board_title=VALUES(board_title),
          stack_id=VALUES(stack_id),
          stack_title=VALUES(stack_title),
          duedate=VALUES(duedate)
        """,
        (
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

def save_task_assignee(card_id, nc_login):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO task_assignees
          (card_id, nc_login)
        VALUES (%s, %s)
        """,
        (card_id, nc_login)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_task_assignees(card_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nc_login FROM task_assignees WHERE card_id = %s", (card_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(row[0] for row in rows)

def get_user_map():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, nc_login FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[1]: row[0] for row in rows}
def get_saved_tasks():
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tasks")
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return {t['card_id']: t for t in tasks}

def update_task_in_db(card_id, title, description, board_id, board_title, stack_id, stack_title, duedate):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks SET
            title=%s, description=%s,
            board_id=%s, board_title=%s,
            stack_id=%s, stack_title=%s,
            duedate=%s
        WHERE card_id=%s
        """,
        (title, description, board_id, board_title, stack_id, stack_title, duedate, card_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

bot = telebot.TeleBot(BOT_TOKEN)

def get_message_thread_id(board_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT message_thread_id FROM board_log_topics WHERE board_id = %s", (board_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return row[0]
    else:
        return BOT_LOG_TOPIC_ID


@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(chat_id, "Эта команда может использоваться только в лс с ботом", message_thread_id=message.message_thread_id)
        return
    if get_login_by_tg_id(message.chat.id)==None:
        send_message_limited(chat_id, "Введите свой логин cloud.joutak.ru:")
    else:
        send_message_limited(chat_id, "Ваш логин уже имеется в базе данных. Если его необходимо сменить - обратитесь к администратору.")

@bot.message_handler(commands=['mycards'])
def show_user_cards(message):
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(chat_id, "Эта команда может использоваться только в лс с ботом", message_thread_id=message.message_thread_id)
        return

    saved_login = get_login_by_tg_id(chat_id)
    if not saved_login:
        send_message_limited(chat_id, "Сначала отправьте логин командой /start.")
        return

    login = saved_login
    send_message_limited(chat_id, "Ищу задачи...")
    tasks = fetch_user_tasks(login)
    for t in tasks:
        save_task_to_db(
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
        send_message_limited(chat_id, msg, reply_markup=kb, parse_mode="Markdown")

def get_board_title(board_id):
    boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    boards_resp.raise_for_status()
    boards = boards_resp.json()
    for board in boards:
        if board.get('id') == board_id:
            return board.get('title')
    return None

@bot.message_handler(commands=['whereami'])
def whereami(m):
    send_message_limited(
        m.chat.id,
        f"Это тема с message_thread_id = {m.message_thread_id}",
        message_thread_id=m.message_thread_id
    )

@bot.message_handler(commands=['chatid'])
def chatid(message):
    send_message_limited(
        message.chat.id,
        f"chat_id = {message.chat.id}",
        message_thread_id=message.message_thread_id
    )
@bot.message_handler(commands=['setboardtopic'])
def set_board_topic_handler(message):
    chat_id = message.chat.id
    if message.chat.type != 'supergroup':
        send_message_limited(chat_id, "Эта команда работает только в группах с топиками.")
        return
    thread_id = getattr(message, 'message_thread_id', None)
    if not thread_id:
        send_message_limited(chat_id, "Команда должна вызываться из конкретного топика.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        send_message_limited(chat_id, "Используйте: /setboardtopic <номер_доски>", message_thread_id=message.message_thread_id)
        return
    try:
        board_id = int(parts[1])
    except ValueError:
        send_message_limited(chat_id, "Номер доски должен быть числом.", message_thread_id=message.message_thread_id)
        return
    board_title = get_board_title(board_id)
    if board_title is None:
        send_message_limited(chat_id, "Номер доски не найден.", message_thread_id=message.message_thread_id)
        return

    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO board_log_topics (board_id, message_thread_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE message_thread_id = VALUES(message_thread_id)
        """, (board_id, thread_id))

        conn.commit()
        cursor.close()
        conn.close()
        send_message_limited(chat_id, f"Этот топик (ID {thread_id}) привязан к доске {board_title} (ID: {board_id})", message_thread_id=message.message_thread_id)
    except Exception as e:
        logging.exception("Ошибка при сохранении топика для доски" +str(e) )

@bot.message_handler(func=lambda msg: get_login_by_tg_id(msg.chat.id) is None)
def save_login(message):
    if message.chat.type != "private":
        return
    chat_id = message.chat.id
    nc_login = message.text.strip()
    save_login_to_db(chat_id, nc_login)
    send_message_limited(chat_id, f"Логин `{nc_login}` сохранён.", parse_mode="Markdown")

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
                    duedate_dt = None
                    if duedate_iso:
                        duedate_dt = datetime.fromisoformat(duedate_iso)
                        duedate_dt = duedate_dt.astimezone(timezone.utc)
                        duedate_dt = duedate_dt.replace(tzinfo=None)

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

def fetch_all_tasks():
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
                duedate_iso = card.get('duedate')
                duedate_dt = None
                if duedate_iso:
                    duedate_dt = datetime.fromisoformat(duedate_iso)
                    duedate_dt = duedate_dt.astimezone(timezone.utc)
                    duedate_dt = duedate_dt.replace(tzinfo=None)

                assigned_logins = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]

                prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None

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
                    'duedate': duedate_dt,
                    'assigned_logins': assigned_logins
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

# def poll_new_tasks():
#     while True:
#         for tg_id, login in get_user_list():
#             conn = get_mysql_connection()
#             cursor = conn.cursor()
#             cursor.execute("SELECT card_id FROM tasks WHERE tg_id = %s", (tg_id,))
#             saved_ids = {r[0] for r in cursor.fetchall()}
#             cursor.close()
#             conn.close()
#
#             current = fetch_user_tasks(login)
#             current_ids = {item['card_id'] for item in current}
#
#             new_ids = current_ids - saved_ids
#
#             for item in current:
#                 if item['card_id'] in new_ids:
#                     save_task_to_db(
#                         tg_id,
#                         item['card_id'],
#                         item['title'],
#                         item['description'],
#                         item['board_id'],
#                         item['board_title'],
#                         item['stack_id'],
#                         item['stack_title'],
#                         item['duedate']
#                     )
#
#                     kb = InlineKeyboardMarkup()
#                     if item['prev_stack_id'] is not None:
#                         kb.add(InlineKeyboardButton(
#                             text=f"⬅ {item['prev_stack_title']}",
#                             callback_data=(
#                                 f"move:{item['board_id']}:"
#                                 f"{item['stack_id']}:"
#                                 f"{item['card_id']}:"
#                                 f"{item['prev_stack_id']}"
#                             )
#                         ))
#                     if item['next_stack_id'] is not None:
#                         kb.add(InlineKeyboardButton(
#                             text=f"➡ {item['next_stack_title']}",
#                             callback_data=(
#                                 f"move:{item['board_id']}:"
#                                 f"{item['stack_id']}:"
#                                 f"{item['card_id']}:"
#                                 f"{item['next_stack_id']}"
#                             )
#                         ))
#                     user_msg = (
#                         f"🆕 Новая задача: *{item['title']}*\n"
#                         f"Board: {item['board_title']}\n"
#                         f"Column: {item['stack_title']}\n"
#                         f"Due: {item['duedate'] or '—'}\n"
#                         f"{item['description'] or '—'}"
#                     )
#                     send_message_limited(
#                         tg_id,
#                         user_msg,
#                         reply_markup=kb,
#                         parse_mode="Markdown"
#                     )
#
#                     topic_msg = (
#                         f"🆕 *Новая задача* у пользователя `{tg_id}`: *{item['title']}*\n"
#                         f"Board: {item['board_title']}\n"
#                         f"Column: {item['stack_title']}\n"
#                         f"Due: `{item['duedate'] or '—'}`"
#                     )
#                     send_log(topic_msg)
#
#         time.sleep(POLL_INTERVAL)


def send_log(text, board_id=None):
    message_thread_id = get_message_thread_id(board_id)
    send_message_limited(
        FORUM_CHAT_ID,
        text,
        parse_mode="Markdown",
        message_thread_id=message_thread_id
    )

def poll_new_tasks():
    MSK = timezone(timedelta(hours=3))
    while True:
        login_map = get_user_map()
        all_cards = fetch_all_tasks()
        saved_tasks = get_saved_tasks()
        for item in all_cards:
            card_id = item['card_id']
            saved = saved_tasks.get(card_id)
            if not saved:
                save_task_basic(
                    card_id, item['title'], item['description'],
                    item['board_id'], item['board_title'],
                    item['stack_id'], item['stack_title'], item['duedate']
                )
            else:
                changes = []
                if saved['stack_id'] != item['stack_id']:
                    changes.append(f"Колонка: *{saved['stack_title']}* → *{item['stack_title']}*")
                UTC = timezone.utc
                od = saved['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if saved['duedate'] else None
                nd = item['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if item['duedate'] else None
                if od != nd:
                    changes.append(f"Due: `{od or '—'}` → `{nd or '—'}`")
                if saved['title'] != item['title']:
                    changes.append(f"Заголовок: `{saved['title']}` → `{item['title']}`")
                if saved['description'] != item['description']:
                    changes.append(f"Описание изменилось")
                if changes:
                    update_task_in_db(
                        card_id, item['title'], item['description'],
                        item['board_id'], item['board_title'],
                        item['stack_id'], item['stack_title'], item['duedate']
                    )
            assigned_logins_db = get_task_assignees(card_id)
            assigned_logins_api = set(item.get('assigned_logins', []))
            new_assignees = assigned_logins_api - assigned_logins_db
            for login in new_assignees:
                save_task_assignee(card_id, login)
            tg_ids = [login_map[login] for login in assigned_logins_api if login in login_map]
            for login in new_assignees:
                tg_id = login_map.get(login)
                if tg_id:
                    kb = InlineKeyboardMarkup()
                    prev_stack_id = item['prev_stack_id']
                    next_stack_id = item['next_stack_id']
                    if prev_stack_id is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"⬅ {item['prev_stack_title']}",
                            callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{prev_stack_id}"
                        ))
                    if next_stack_id is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"➡ {item['next_stack_title']}",
                            callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{next_stack_id}"
                        ))
                    user_msg = (
                        f"🆕 Новая задача: *{item['title']}*\n"
                        f"Board: {item['board_title']}\n"
                        f"Column: {item['stack_title']}\n"
                        f"Due: {item['duedate'] or '—'}\n"
                        f"{item['description'] or '—'}"
                    )
                    send_message_limited(
                        tg_id,
                        user_msg,
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )
            if not saved:
                for tg_id in tg_ids:
                    kb = InlineKeyboardMarkup()
                    prev_stack_id = item['prev_stack_id']
                    next_stack_id = item['next_stack_id']
                    if prev_stack_id is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"⬅ {item['prev_stack_title']}",
                            callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{prev_stack_id}"
                        ))
                    if next_stack_id is not None:
                        kb.add(InlineKeyboardButton(
                            text=f"➡ {item['next_stack_title']}",
                            callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{next_stack_id}"
                        ))
                    user_msg = (
                        f"🆕 Новая задача: *{item['title']}*\n"
                        f"Board: {item['board_title']}\n"
                        f"Column: {item['stack_title']}\n"
                        f"Due: {item['duedate'] or '—'}\n"
                        f"{item['description'] or '—'}"
                    )
                    send_message_limited(
                        tg_id,
                        user_msg,
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )
                send_log(
                    f"🆕 *Новая задача*: {item['title']}\n"
                    f"Board: {item['board_title']}\n"
                    f"Column: {item['stack_title']}\n"
                    f"Due: {item['duedate'] or '—'}",
                    board_id=item['board_id']
                )
            else:
                if changes:
                    for tg_id in tg_ids:
                        send_message_limited(
                            tg_id,
                            f"✏️ *Изменения в карточке* «{item['title']}» (ID `{card_id}`):\n" + "\n".join(changes),
                            parse_mode="Markdown"
                        )
                    send_log(
                        f"✏️ *Изменения в карточке* «{item['title']}» (ID `{card_id}`):\n" + "\n".join(changes),
                        board_id=item['board_id']
                    )
        time.sleep(POLL_INTERVAL)







if __name__ == "__main__":
    t = threading.Thread(target=poll_new_tasks, daemon=True)
    t.start()

    bot.polling()
