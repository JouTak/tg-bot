import time
from datetime import timezone, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from source.config import POLL_INTERVAL
from source.connections.sender import send_message_limited
from source.connections.nextcloud_api import fetch_all_tasks
from source.db.repos.users import get_user_map
from source.db.repos.tasks import (
    get_saved_tasks, save_task_basic, update_task_in_db,
    get_task_assignees, save_task_assignee
)
from source.app_logging import logger
from source.logging_service import send_log
from source.formatting import mdv2_escape as e, mdv2_code as c


def poll_new_tasks():
    logger.info(f"CLOUD: Запускается фоновый опрос задач, частота: {POLL_INTERVAL} секунд!")
    MSK = timezone(timedelta(hours=3))
    while True:
        logger.info(f"CLOUD: Начинается плановое получение задач")
        changes_flag = False
        login_map = get_user_map()
        all_cards = fetch_all_tasks()
        saved_tasks = get_saved_tasks()
        for item in all_cards:
            card_id = item['card_id']
            saved = saved_tasks.get(card_id)
            if not saved:
                changes_flag = True
                save_task_basic(
                    card_id, item['title'], item['description'],
                    item['board_id'], item['board_title'],
                    item['stack_id'], item['stack_title'], item['duedate']
                )
            else:
                changes = []
                if saved['stack_id'] != item['stack_id']:
                    changes.append(f"Колонка: *{e(saved['stack_title'])}* → *{e(item['stack_title'])}*")
                UTC = timezone.utc
                od = saved['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if saved['duedate'] else None
                nd = item['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if item['duedate'] else None
                if od != nd:
                    changes.append(f"Due: `{c(od or '—')}` → `{c(nd or '—')}`")
                if saved['title'] != item['title']:
                    changes.append(f"Заголовок: `{c(saved['title'])}` → `{c(item['title'])}`")
                if saved['description'] != item['description']:
                    changes.append(f"Описание изменилось")
                if changes:
                    changes_flag = True
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
                        parse_mode="MarkdownV2"
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
                        parse_mode="MarkdownV2"
                    )
                send_log(
                    f"🆕 *Новая задача*: {e(item['title'])}\n"
                    f"Board: {e(item['board_title'])}\n"
                    f"Column: {e(item['stack_title'])}\n"
                    f"Due: {c(item['duedate']) or '—'}",
                    board_id=item['board_id']
                )
            else:
                if changes:
                    for tg_id in tg_ids:
                        send_message_limited(
                            tg_id,
                            f"✏️ *Изменения в карточке* «{e(item['title'])}» — ID `{e(card_id)}`:\n" + "\n".join(changes),
                            parse_mode="MarkdownV2"
                        )
                    send_log(
                        f"✏️ *Изменения в карточке* «{e(item['title'])}» — ID `{e(card_id)}`:\n" + "\n".join(changes),
                        board_id=item['board_id']
                    )

        logger.info("CLOUD: " + ("изменения найдены." if changes_flag else "изменений не обнаружено."))
        time.sleep(POLL_INTERVAL)
