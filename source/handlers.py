from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from source.app_logging import logger
from source.connections.bot_factory import bot
from source.connections.sender import send_message_limited
from source.db.repos.users import get_login_by_tg_id, save_login_to_db
from source.db.repos.tasks import save_task_to_db, get_tasks_from_users
from source.db.repos.boards import save_board_topic
from source.connections.nextcloud_api import fetch_user_tasks, get_board_title


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
    logger.info("Поступила команда /mycards")
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
    tasks = get_tasks_from_users(login)
    flag_is_need_get_information = False

    for t in tasks:
        if (t['prev_stack_id'] is None) and (t['next_stack_id'] is None):
            flag_is_need_get_information = True
            tasks = fetch_user_tasks(login)
            break

    for t in tasks:
        if flag_is_need_get_information:
            save_task_to_db(
                t['card_id'],
                t['title'],
                t['description'],
                t['board_id'],
                t['board_title'],
                t['stack_id'],
                t['stack_title'],
                t['prev_stack_id'],
                t['prev_stack_title'],
                t['next_stack_id'],
                t['next_stack_title'],
                t['duedate'],
                t['done'],
                t['etag']
            )
        if t['stack_title'] == "готово":
            print("kek")
            continue

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
        send_message_limited(chat_id, msg, reply_markup=kb)

@bot.message_handler(commands=['whereami'])
def whereami(m):
    send_message_limited(
        m.chat.id,
        f"Ты находишься в чате с chat_id = {m.chat.id}\n"
        f"Это тема с message_thread_id = {m.message_thread_id}",
        message_thread_id=m.message_thread_id
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
    save_board_topic(board_id, thread_id)
    send_message_limited(chat_id, f"Этот топик (ID {thread_id}) привязан к доске {board_title} (ID: {board_id})", message_thread_id=message.message_thread_id)

@bot.message_handler(func=lambda msg: bool(getattr(msg, "text", "")) and not msg.text.startswith('/'))
def save_login(message):
    if message.chat.type != "private":
        return
    logger.info(f"Свободный текст в ЛС (сохранение логина) от user_id={message.from_user.id} ({message.from_user.username}):\n{message.text}")
    if get_login_by_tg_id(message.chat.id) is not None:
        return
    chat_id = message.chat.id
    nc_login = message.text.strip()
    save_login_to_db(chat_id, nc_login)
    send_message_limited(chat_id, f"Логин `{nc_login}` сохранён.")