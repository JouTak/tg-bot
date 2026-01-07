import time
import re
import difflib
import traceback
from datetime import timezone, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from source.config import POLL_INTERVAL
from source.connections.sender import send_message_limited
from source.connections.nextcloud_api import fetch_all_tasks
from source.db.repos.users import get_user_map
from source.db.repos.tasks import (
    get_saved_tasks, save_task_basic, update_task_in_db,
    get_task_assignees, save_task_assignee,
    get_task_stats_map, upsert_task_stats
)
from source.app_logging import logger
from source.logging_service import send_log
from source.links import card_url


def change_description(old_description, new_description):
    result_txt = ''; add_text = ''; remove_text = ''; change_text = ''
    if ('[ ]' in new_description) or ('[x]' in new_description):
        old_desc = old_description.split('\n')
        new_desc = new_description.split('\n')
        def find_changes(desc, desription, sign, format):
            result = ''
            for point in range(len(desc)):
                if desc[point][5:] not in desription:
                    if desc[point][:2] == '- ':
                        result += f'\\\\\\{format}{sign} ' + desc[point][2:] + f'{format}///\n'
                    else:
                        result += f'\\\\\\{format}{sign} ' + desc[point] + f'{format}///\n'
                    desc[point] = ''
            if result != '':
                if result[-1] == '\n': result = result[:-1]
            return result

        remove_text = find_changes(old_desc, new_description, '-', '~')
        add_text = find_changes(new_desc, old_description, '+', '*')
        point = 0
        while point != max(len(old_desc), len(new_desc)):
            try:
                if old_desc[point][3] != new_desc[point][3]:
                    change_text += '\\\\\\_& ' + new_desc[point][2:] + '_///\n'
                point += 1
            except IndexError:
                break
        if change_text != '':
            if change_text[-1] == '\n': change_text = change_text[:-1]
    else:
        old_desc = re.split(r"[.!?;\n]+", old_description)
        new_desc = re.split(r"[.!?;\n]+", new_description)
        diff = difflib.ndiff(old_desc, new_desc)
        for d in diff:
            if d[2:].lstrip() == '':
                continue
            if d.startswith("+ "):
                add_text += "\\\\\\*" + d[2:].lstrip() + '*///\n'
            elif d.startswith("- "):
                remove_text += "\\\\\\~" + d[2:].lstrip() + '~///\n'
        if len(add_text) > 0:
            if add_text[-1] == '\n': add_text = add_text[:-1]
        if len(remove_text) > 0:
            if remove_text[-1] == '\n': remove_text = remove_text[:-1]
    if len(add_text) > 0:
        result_txt += f"{add_text}\n"
    if len(remove_text) > 0:
        result_txt += f"{remove_text}\n"
    if len(change_text) > 0:
        result_txt += f"{change_text}\n"
    return result_txt


def poll_new_tasks():
    logger.info(f"CLOUD: Запускается фоновый опрос задач, частота: {POLL_INTERVAL} секунд!")
    MSK = timezone(timedelta(hours=3))
    while True:
        try:
            logger.info(f"CLOUD: Начинается плановое получение задач")
            changes_flag = False
            login_map = get_user_map()
            all_cards = fetch_all_tasks()
            saved_tasks = get_saved_tasks()
            stats_map = get_task_stats_map()

            for item in all_cards:
                changes = []
                card_id = item['card_id']; board_id = item['board_id']
                cid_link = f'<a href="{card_url(item["board_id"], card_id)}">{card_id}</a>'

                new_comments = int(item.get('comments_count', 0))
                new_attachments = int(item.get('attachments_count', 0))

                saved = saved_tasks.get(card_id)

                etag_new = item.get('etag')
                etag_old = saved.get('etag') if saved else None
                etag_same = bool(saved and (etag_new is not None) and (etag_old == etag_new))

                if not saved:
                    changes_flag = True
                    save_task_basic(
                        card_id, item['title'], item['description'],
                        item['board_id'], item['board_title'],
                        item['stack_id'], item['stack_title'], item['duedate'], etag_new
                    )
                    upsert_task_stats(card_id, new_comments, new_attachments)
                    stats_map[card_id] = {
                        "comments_count": new_comments,
                        "attachments_count": new_attachments
                    }
                elif not etag_same:
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
                        text = change_description(saved['description'], item['description'])
                        changes.append(f"Описание изменилось: \n{text}")

                    if changes or (etag_old is None) or (etag_new is None):
                        changes_flag = True
                        update_task_in_db(
                            card_id, item['title'], item['description'],
                            item['board_id'], item['board_title'],
                            item['stack_id'], item['stack_title'], item['duedate'], etag_new
                        )

                    old_stats = stats_map.get(card_id, {"comments_count": 0, "attachments_count": 0})
                    inc_comments = new_comments - int(old_stats.get('comments_count', 0))
                    inc_attachments = new_attachments - int(old_stats.get('attachments_count', 0))

                    if inc_comments > 0:
                        send_log(
                            "💬 Новые комментарии:" + "\n"
                            f"{inc_comments} в «{item['title']}» (ID: {cid_link})",
                            board_id=item['board_id']
                        )
                    elif inc_comments < 0:
                        send_log(
                            "🗑 Удалены комментарии: "+"\n"
                            f"{-inc_comments} в «{item['title']}» (ID: {cid_link})",
                            board_id=item['board_id'])

                    if inc_attachments > 0:
                        send_log(
                            "📎 Новые вложения:" + "\n"
                            f"{inc_attachments} в «{item['title']}» (ID: {cid_link})",
                            board_id=item['board_id']
                        )
                    elif inc_attachments < 0:
                        send_log(
                            "🗑 Удалены вложения: "+"\n"
                            f" {-inc_attachments} в «{item['title']}» (ID: {cid_link})",
                            board_id=item['board_id'])

                    if (inc_comments != 0) or (inc_attachments != 0) or (card_id not in stats_map):
                        upsert_task_stats(card_id, new_comments, new_attachments)
                        stats_map[card_id] = {"comments_count": new_comments, "attachments_count": new_attachments}

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
                            f"{item['description'] or '-'}"
                        )
                        kb.add(InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                        send_message_limited(
                            tg_id,
                            user_msg,
                            reply_markup=kb,
                        )

                if not saved:
                    send_log(
                        f"🆕 *Новая задача* c ID {cid_link}: {item['title']}\n"
                        f"Board: {item['board_title']}\n"
                        f"Column: {item['stack_title']}\n"
                        f"Due: {item['duedate'] or '—'}",
                        board_id=item['board_id']
                    )
                else:
                    if changes:
                        for tg_id in tg_ids:
                            kb = InlineKeyboardMarkup()
                            kb.add(InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                            send_message_limited(
                                tg_id,
                                f"✏️ *Изменения в карточке* «{item['title']}» (ID {cid_link}):\n" + "\n".join(changes),
                                reply_markup=kb,
                            )
                        send_log(
                            f"✏️ *Изменения в карточке* «{item['title']}» (ID {cid_link}):\n" + "\n".join(changes),
                            board_id=item['board_id']
                        )

            logger.info("CLOUD: " + ("изменения найдены." if changes_flag else "изменений не обнаружено."))
        except Exception as e:
            logger.error(f"CLOUD: ошибка плановой обработки задач — {e}")
            logger.debug(traceback.format_exc())
        time.sleep(POLL_INTERVAL)
