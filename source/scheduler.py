import time
import re
import difflib
import traceback
from datetime import timezone, timedelta
from collections import Counter
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from source.config import POLL_INTERVAL, EXCLUDED_CARD_IDS
from source.connections.sender import send_message_limited
from source.connections.nextcloud_api import fetch_all_tasks, in_done_stack
from source.db.repos.users import get_user_map
from source.db.repos.tasks import (
    get_saved_tasks, save_task_to_db, update_task_in_db,
    get_task_assignees, save_task_assignee,
    get_task_stats_map, upsert_task_stats
)
from source.app_logging import logger, is_debug
from source.logging_service import send_log
from source.links import card_url


def change_description(old_description, new_description):
    """
    Анализирует изменения описания карточки.
    Выявляет:
    - добавленные пункты
    - удалённые пункты
    - изменённые чекбоксы

    Возвращает текст различий для уведомления.
    """
    result_txt = ''
    add_text = ''
    remove_text = ''
    change_text = ''
    split_pattern = (
        r'(?<=[.!?])(?<!\d\.)\s+(?=[А-ЯA-Z0-9])'
        r'|[\s\n]{2,}'
        r'|[\r\n]+(?=\s*[-*+]\s+\[)'
    )
    old_desc = re.split(split_pattern, old_description.strip())
    old_desc = [s.strip() for s in old_desc if s.strip()]

    new_desc = re.split(split_pattern, new_description.strip())
    new_desc = [s.strip() for s in new_desc if s.strip()]
    checkbox_pattern = re.compile(r'^\s*[-*+]\s+\[([ xX])\]\s+(.*)')

    def is_checkbox(text):
        return checkbox_pattern.match(text) is not None

    diff = list(difflib.ndiff(old_desc, new_desc))
    count_checkbox = Counter()

    for checkbox in diff:
        text = checkbox[2:]
        if is_checkbox(text):
            count_checkbox[text[6:]] += 1

    for d in diff:
        if d[2:].lstrip() == '':
            continue
        if d.startswith("+ "):
            if is_checkbox(d[2:]) and count_checkbox[d[8:]] >= 2:
                add_text += "\\\\\\_& " + d[4:].lstrip() + '_///\n'
            elif is_checkbox(d[2:]):
                add_text += "\\\\\\*+ " + d[4:].lstrip() + '*///\n'
            else:
                add_text += "\\\\\\*" + d[2:].lstrip() + '*///\n'
        elif d.startswith("- "):
            if is_checkbox(d[2:]) and count_checkbox[d[8:]] == 1:
                remove_text += "\\\\\\~- " + d[4:].lstrip() + '~///\n'
            elif not (is_checkbox(d[2:])):
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


def _should_notify(card_id: int) -> bool:
    """Возвращает True, если по карточке можно отправлять уведомления."""
    return card_id not in EXCLUDED_CARD_IDS


def poll_new_tasks():
    """
    Фоновый процесс:
    - получает все задачи из Nextcloud
    - сравнивает с БД
    - определяет новые и изменённые карточки
    - отправляет уведомления (кроме исключённых)
    - обновляет статистику комментариев и вложений
    """
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
                card_id = item.get('card_id')
                board_id = item.get('board_id')
                cid_link = f'<a href="{card_url(item.get("board_id"), card_id)}">{card_id}</a>'

                new_comments = int(item.get('comments_count', 0))
                new_attachments = int(item.get('attachments_count', 0))

                saved = saved_tasks.get(card_id)

                etag_new = item.get('etag')
                etag_old = saved.get('etag') if saved else None
                etag_same = bool(saved and (etag_new is not None) and (etag_old == etag_new))

                need_mig_update = bool(
                    saved and (saved.get('prev_stack_id') is None) and (saved.get('next_stack_id') is None)
                )

                if is_debug():
                    need_cooldown = False
                else:
                    need_cooldown = item['lastModified'] < POLL_INTERVAL

                if need_cooldown:
                    continue

                # === БД-операции выполняются ВСЕГДА, независимо от исключений ===
                if not saved:
                    changes_flag = True
                    save_task_to_db(
                        card_id, item['title'], item['description'],
                        item['board_id'], item['board_title'],
                        item['stack_id'], item['stack_title'],
                        item.get('prev_stack_id'), item.get('prev_stack_title'),
                        item.get('next_stack_id'), item.get('next_stack_title'),
                        item.get('duedate'), item.get('done'), etag_new
                    )
                    upsert_task_stats(card_id, new_comments, new_attachments)
                    stats_map[card_id] = {
                        "comments_count": new_comments,
                        "attachments_count": new_attachments
                    }
                elif not etag_same:
                    if item['done'] and item['next_stack_id'] is not None:
                        info = in_done_stack(item)
                        if info is not None:
                            item['stack_title'], item['stack_id'] = info
                            item['prev_stack_id'], item['next_stack_id'], item['prev_stack_title'], item[
                                'next_stack_title'] = None, None, None, None
                    if saved['stack_id'] != item['stack_id']:
                        changes.append(f"Колонка: *{saved['stack_title']}* → *{item['stack_title']}*")
                    UTC = timezone.utc
                    od = saved['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if saved[
                        'duedate'] else None
                    nd = item['duedate'].replace(tzinfo=UTC).astimezone(MSK).strftime("%y-%m-%d %H:%M") if item[
                        'duedate'] else None
                    if od != nd:
                        changes.append(f"Due: `{od or '—'}` → `{nd or '—'}`")
                    if saved['title'] != item['title']:
                        changes.append(f"Заголовок: `{saved['title']}` → `{item['title']}`")
                    if saved['description'] != item['description']:
                        text = change_description(saved['description'], item['description'])
                        changes.append(f"Описание изменилось: \n{text}")

                    if changes or (etag_old is None) or (etag_new is None) or need_mig_update:
                        changes_flag = True
                        update_task_in_db(
                            card_id, item['title'], item['description'],
                            item['board_id'], item['board_title'],
                            item['stack_id'], item['stack_title'],
                            item.get('prev_stack_id'), item.get('prev_stack_title'),
                            item.get('next_stack_id'), item.get('next_stack_title'),
                            item.get('duedate'), item.get('done'), etag_new
                        )

                    old_stats = stats_map.get(card_id, {"comments_count": 0, "attachments_count": 0})
                    inc_comments = new_comments - int(old_stats.get('comments_count', 0))
                    inc_attachments = new_attachments - int(old_stats.get('attachments_count', 0))

                    # === Уведомления о комментариях/вложениях ТОЛЬКО если не в исключениях ===
                    if _should_notify(card_id):
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                        if inc_comments > 0:
                            send_log(
                                "💬 Новые комментарии:" + "\n"
                                                          f"{inc_comments} в «{item['title']}»",
                                board_id=item['board_id'],
                                reply_markup=kb,
                            )
                        elif inc_comments < 0:
                            send_log(
                                "🗑 Удалены комментарии: " + "\n"
                                                             f"{-inc_comments} в «{item['title']}»",
                                board_id=item['board_id'],
                                reply_markup=kb,
                            )

                        if inc_attachments > 0:
                            send_log(
                                "📎 Новые вложения:" + "\n"
                                                       f"{inc_attachments} в «{item['title']}»",
                                board_id=item['board_id'],
                                reply_markup=kb,
                            )
                        elif inc_attachments < 0:
                            send_log(
                                "🗑 Удалены вложения: " + "\n"
                                                          f" {-inc_attachments} в «{item['title']}»",
                                board_id=item['board_id'],
                                reply_markup=kb,
                            )

                    if (inc_comments != 0) or (inc_attachments != 0) or (card_id not in stats_map):
                        upsert_task_stats(card_id, new_comments, new_attachments)
                        stats_map[card_id] = {"comments_count": new_comments, "attachments_count": new_attachments}
                elif need_mig_update:
                    update_task_in_db(
                        card_id, item['title'], item['description'],
                        item['board_id'], item['board_title'],
                        item['stack_id'], item['stack_title'],
                        item.get('prev_stack_id'), item.get('prev_stack_title'),
                        item.get('next_stack_id'), item.get('next_stack_title'),
                        item.get('duedate'), item.get('done'), etag_new
                    )

                # === Работа с назначенными (БД) — всегда ===
                assigned_logins_db = get_task_assignees(card_id)
                assigned_logins_api = set(item.get('assigned_logins', []))
                new_assignees = assigned_logins_api - assigned_logins_db
                for login in new_assignees:
                    save_task_assignee(card_id, login)

                tg_ids = [login_map[login] for login in assigned_logins_api if login in login_map]

                # === Уведомления новым назначенным ТОЛЬКО если не в исключениях ===
                if _should_notify(card_id):
                    for login in new_assignees:
                        tg_id = login_map.get(login)
                        if tg_id:
                            kb = InlineKeyboardMarkup()
                            prev_stack_id = item.get('prev_stack_id')
                            next_stack_id = item.get('next_stack_id')
                            if prev_stack_id is not None:
                                kb.add(InlineKeyboardButton(
                                    text=f"⬅ {item.get('prev_stack_title')}",
                                    callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{prev_stack_id}"
                                ))
                            if next_stack_id is not None:
                                kb.add(InlineKeyboardButton(
                                    text=f"➡ {item.get('next_stack_title')}",
                                    callback_data=f"move:{item['board_id']}:{item['stack_id']}:{card_id}:{next_stack_id}"
                                ))
                            user_msg = (
                                f"🆕 Новая задача: *{item['title']}*\n"
                                f"Board: {item['board_title']}\n"
                                f"Column: {item['stack_title']}\n"
                                f"Due: {item['duedate'] or '—'}\n"
                                f"Description: \n\\\\\\{item['description'] or '-'}///"
                            )
                            kb.add(
                                InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                            send_message_limited(
                                tg_id,
                                user_msg,
                                reply_markup=kb,
                            )

                # === Уведомление о новой задаче в лог ТОЛЬКО если не в исключениях ===
                if not saved and _should_notify(card_id):
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                    send_log(
                        f"🆕 *Новая задача*: {item['title']}\n"
                        f"Board: {item['board_title']}\n"
                        f"Column: {item['stack_title']}\n"
                        f"Due: {item['duedate'] or '—'}\n"
                        f"Description: \n\\\\\\{item['description'] or '-'}///",
                        board_id=item['board_id'],
                        reply_markup=kb,
                    )
                # === Уведомления об изменениях ТОЛЬКО если не в исключениях ===
                elif saved and changes and _should_notify(card_id):
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton(text="Открыть на клауде", url=card_url(item["board_id"], card_id)))
                    for tg_id in tg_ids:
                        send_message_limited(
                            tg_id,
                            f"✏️ *Изменения в карточке* «{item['title']}» (ID {cid_link}):\n" + "\n".join(changes),
                            reply_markup=kb,
                        )
                    send_log(
                        f"✏️ *Изменения в карточке* «{item['title']}»:\n" + "\n".join(changes),
                        board_id=item['board_id'],
                        reply_markup=kb,
                    )

            logger.info("CLOUD: " + ("изменения найдены." if changes_flag else "изменений не обнаружено."))
        except Exception as e:
            logger.error(f"CLOUD: ошибка плановой обработки задач — {e}")
            logger.debug(traceback.format_exc())
        time.sleep(POLL_INTERVAL)
