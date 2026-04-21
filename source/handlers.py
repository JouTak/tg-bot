from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReactionTypeEmoji)

from source.app_logging import logger
from source.connections.bot_factory import bot
from source.connections.sender import send_message_limited
from source.db.repos.users import get_login_by_tg_id, save_login_to_db, save_login_token, delete_login_token, get_token, get_nc_token
from source.db.repos.tasks import save_task_to_db, get_tasks_from_users, save_task_comment, get_task_stat, upsert_task_stats
from source.db.repos.boards import save_board_topic
from source.connections.nextcloud_api import fetch_user_tasks, get_board_title
from source.config import COMMIT_HASH, WEB_APP_URL, OCS_BASE_URL, HEADERS

from requests import post

@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(chat_id, "Эта команда может использоваться только в лс с ботом",
                             message_thread_id=message.message_thread_id)
        return
    else: #нужна кнопочка
        send_message_limited(chat_id, "Этот бот создан специально для организаторов клуба @ITMOcraft! Если ты у нас в команде, регистрируйся в боте через команду /register. \n\nИнтересует вступление в команду организаторов? Заполняй анкету: https://forms.yandex.ru/u/67773408068ff0452320c8b4!")

@bot.message_handler(commands=['register'])
def register_handler(message):
    """
    Обрабатывает команду /register.
    Запрашивает логин Nextcloud, если он ещё не сохранён.
    """
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(chat_id, "Эта команда может использоваться только в лс с ботом",
                             message_thread_id=message.message_thread_id)
        return
    if (get_login_by_tg_id(message.from_user.id) == None) or (get_login_by_tg_id(message.from_user.id) != None and get_nc_token(message.from_user.id) == None):
        markup = InlineKeyboardMarkup()
        headers = {
            'User-Agent': '@ITMOcraftBOT',
            'Accept': 'application/json'
        }
        init_resp = post(WEB_APP_URL + "/index.php/login/v2", headers=headers)
        init_resp.raise_for_status()
        init_resp = init_resp.json()
        login_url = init_resp['login']
        poll_token = init_resp['poll']['token']

        delete_login_token(message.from_user.id)

        save_login_token(message.from_user.id, poll_token)
        web_app = WebAppInfo(login_url)
        btn = InlineKeyboardButton("Подключить Cloud", web_app=web_app)
        btn_check = InlineKeyboardButton("Подтвердить вход ✅", callback_data=f"check")
        markup.add(btn)
        markup.add(btn_check)
        send_message_limited(chat_id, "Авторизуйтесь через клауд:", reply_markup=markup)
    else:
        send_message_limited(chat_id, "Ваш логин уже имеется в базе данных. "
                                      "Если его необходимо сменить - обратитесь к администратору.")


@bot.message_handler(commands=['mycards'])
def show_user_cards(message):
    """
    Обрабатывает команду /mycards.
    Отправляет пользователю список его активных карточек
    с кнопками перемещения между колонками.
    """
    logger.info("Поступила команда /mycards")
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(chat_id, "Эта команда может использоваться только в лс с ботом",
                             message_thread_id=message.message_thread_id)
        return
    saved_login = get_login_by_tg_id(chat_id)
    if not saved_login:
        send_message_limited(chat_id, "Сначала отправьте логин командой /start.")
        return
    login = saved_login
    send_message_limited(chat_id, "Ищу задачи...")
    tasks = get_tasks_from_users(login)

    for t in tasks:
        if t.get('done') is not None:
            continue

        kb = InlineKeyboardMarkup()
        if t.get('prev_stack_id') is not None:
            kb.add(InlineKeyboardButton(
                text=f"⬅ {t.get('prev_stack_title')}",
                callback_data=f"move:{t['board_id']}:{t['stack_id']}:{t['card_id']}:{t.get('prev_stack_id')}"
            ))
        if t.get('next_stack_id') is not None:
            kb.add(InlineKeyboardButton(
                text=f"➡ {t.get('next_stack_title')}",
                callback_data=f"move:{t['board_id']}:{t['stack_id']}:{t['card_id']}:{t.get('next_stack_id')}"
            ))
        msg = (
            f"{t['title']}\n"
            f"Board: {t['board_title']}\n"
            f"Column: {t['stack_title']}\n"
            f"Due: {t['duedate'] or '—'}\n"
            f"{t['description'] or '—'}"
        )
        send_message_limited(chat_id, msg, reply_markup=kb)


@bot.message_handler(commands=['commit'])
def commit_handler(message):
    """
    Показывает текущий коммит или сообщает о локальном билде.
    Работает только в ЛС.
    """
    chat_id = message.chat.id
    if message.chat.type != "private":
        send_message_limited(
            chat_id,
            "Эта команда может использоваться только в лс с ботом",
            message_thread_id=message.message_thread_id,
        )
        return
    if COMMIT_HASH and COMMIT_HASH != "unknown":
        send_message_limited(chat_id, f"Текущий коммит: `{COMMIT_HASH}`")
    else:
        send_message_limited(chat_id, "Бот запущен на локальном билде")


@bot.message_handler(commands=['whereami'])
def whereami(m):
    """
    Команда /whereami.
    Показывает chat_id и message_thread_id.
    Используется для настройки.
    """
    send_message_limited(
        m.chat.id,
        f"Ты находишься в чате с chat_id = {m.chat.id}\n"
        f"Это тема с message_thread_id = {m.message_thread_id}",
        message_thread_id=m.message_thread_id
    )


@bot.message_handler(commands=['setboardtopic'])
def set_board_topic_handler(message):
    """
    Привязывает Telegram-топик к доске Nextcloud.
    Нужно для отправки логов в правильную тему.
    """
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
        send_message_limited(chat_id, "Используйте: /setboardtopic <номер_доски>",
                             message_thread_id=message.message_thread_id)
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
    send_message_limited(chat_id, f"Этот топик (ID {thread_id}) привязан к доске {board_title} (ID: {board_id})",
                         message_thread_id=message.message_thread_id)


@bot.message_handler(func=lambda msg: bool(getattr(msg, "text", "")) and not msg.text.startswith('/') and msg.reply_to_message and msg.chat.type != "private" and msg.reply_to_message.from_user.id == bot.get_me().id)
def reply_comments(message):
    chat_id = message.chat.id
    if (get_login_by_tg_id(message.from_user.id) == None) or (get_login_by_tg_id(message.from_user.id) != None and get_nc_token(message.from_user.id) == None):
        send_message_limited(chat_id, "Бот хочет отправить ответ на эту карточку, однако не может, так как ты не зарегистрирован новым способом. Пожалуйста, зарегистрируй|мигрируй свой аккаунт командой /register в лс с ботом")
        return

    keyboard = message.reply_to_message.reply_markup
    if keyboard is None:
        return
    keyboard_url = keyboard.keyboard[0][0].url
    card_id = int(keyboard_url.split("card/")[1])
    username = get_login_by_tg_id(message.from_user.id)
    token = get_nc_token(message.from_user.id)
    header = {'OCS-APIRequest': 'true', 'Content-Type': 'application/json', 'Accept': 'application/json'}
    comment = post(f"{OCS_BASE_URL}/deck/api/v1.0/cards/{card_id}/comments", headers=header, auth=(username, token), json={"message":message.text, "parentId": None})
    if comment.status_code == 404:
        return
    comment.raise_for_status()
    comment_info = comment.json()
    comment_id = comment_info.get('ocs', {}).get('data', {}).get('id')
    save_task_comment(card_id, comment_id)

    count_commnets_and_attachments = get_task_stat(card_id)
    upsert_task_stats(card_id, count_commnets_and_attachments[0] + 1, count_commnets_and_attachments[1])

    bot.set_message_reaction(chat_id, message.id, [ReactionTypeEmoji(emoji="🙏")], is_big=False)

@bot.message_handler(func=lambda msg: bool(getattr(msg, "text", "")) and not msg.text.startswith('/'))
def save_login(message):
    """
    DEPRECATED
    Сохраняет логин Nextcloud, отправленный пользователем в личные сообщения.
    """
    if message.chat.type != "private":
        return
    logger.info(f"Свободный текст в ЛС от user_id={message.from_user.id} "
                f"({message.from_user.username}):\n{message.text}")
    if get_login_by_tg_id(message.chat.id) is not None:
        return
    chat_id = message.chat.id
    #nc_login = message.text.strip()
    #save_login_to_db(chat_id, nc_login)
    send_message_limited(chat_id, f"Этот бот создан специально для организаторов клуба @ITMOcraft! Если ты у нас в команде, регистрируйся в боте через команду /register. \n\nИнтересует вступление в команду организаторов? Заполняй анкету: https://forms.yandex.ru/u/67773408068ff0452320c8b4!")
