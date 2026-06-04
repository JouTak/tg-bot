from source.config import WEB_CALDAV_URL, USERNAME, PASSWORD, COOLDOWN_TUESDAY, COOLDOWN_SUNDAY, COOLDOWN_DEFAULT, \
    POLL_INTERVAL, WEB_APP_URL, UPDATE_INTERVAL, TIMEZONE
from source.connections.sender import send_message_limited
from source.db.repos.users import get_tg_id_by_email, save_email_by_username
from source.app_logging import logger
from source.db.repos.caldav_calendar import get_events_from_db, save_event_sends, delete_event_sends, get_id_by_name
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from caldav import DAVClient, error
from icalendar import Calendar, vText
from datetime import datetime, timedelta, timezone

from time import sleep
from zoneinfo import ZoneInfo

import requests

try:
    TEAM_TZ = ZoneInfo(TIMEZONE)
except Exception:
    TEAM_TZ = timezone(timedelta(hours=3))

PARSTAT_RU = {
    "ACCEPTED": "Будет",
    "DECLINED": "Не будет",
    "TENTATIVE": "Под вопросом",
    "NEEDS-ACTION": "Неизвестно"
}


def format_to_need_timezone(dt):
    """Приводит время к МСК и форматирует в ЧЧ:ММ"""
    if not isinstance(dt, datetime):
        return str(dt)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(TEAM_TZ).strftime("%H:%M")

def sync_nextcloud_users():
    """
    Получает всех пользователей из Nextcloud и обновляет их данные в БД.
    ВНИМАНИЕ: Пользователь (USERNAME), указанный в конфиге,
    должен иметь права Администратора в Nextcloud.
    """
    headers = {
        "OCS-APIRequest": "true",
        "Accept": "application/json"
    }

    auth = (USERNAME, PASSWORD)
    while True:
        logger.info(f"NEXTCLOUD: Начинаю синхронизацию пользователей (частота {UPDATE_INTERVAL} дней)...")
        try:

            users_endpoint = f"{WEB_APP_URL}/ocs/v1.php/cloud/users?limit=1000"
            response = requests.get(users_endpoint, headers=headers, auth=auth)

            if response.status_code != 200:
                logger.error(
                    f"CLOUD: Ошибка доступа к API. Код: {response.status_code}. Проверьте, является ли {USERNAME} админом.")
                return

            data = response.json()
            try:
                user_ids = data.get('ocs', {}).get('data', {}).get('users', {})
            except AttributeError:
                return

            updated_count = 0
            for uid in user_ids:
                detail_endpoint = f"{WEB_APP_URL}/ocs/v1.php/cloud/users/{uid}"
                detail_res = requests.get(detail_endpoint, headers=headers, auth=auth)
                detail_res.raise_for_status()
                if detail_res.status_code == 200:
                    user_data = detail_res.json().get('ocs', {}).get('data', {})
                    try:
                        email = user_data.get('email', '').strip().lower()
                    except AttributeError:
                        continue
                    if email:
                        save_email_by_username(
                            nc_login=uid,
                            nc_email=email,
                        )
                        updated_count += 1

            logger.info(f"CLOUD: Успешно синхронизировано {updated_count} пользователей с почтой.")
            sleep(86400 * UPDATE_INTERVAL)

        except Exception as e:
            logger.exception(f"CLOUD: Критическая ошибка при синхронизации пользователей: {e}")

def get_all_participants(component):
    """
    Получает организатора и всех участников события.
    Возвращает список словарей с нормализованными email и именами.
    """
    participants = []

    organizer = component.get("organizer")
    if organizer:
        email = str(organizer).lower().replace("mailto:", "")
        name = str(organizer.params.get("CN", email))
        participants.append({
            "email": email,
            "name": name,
            "role": "ORGANIZER",
            "status": "ACCEPTED"
        })

    attendees = component.get("attendee")
    if attendees:
        if not isinstance(attendees, list):
            attendees = [attendees]

        for a in attendees:
            email = str(a).lower().replace("mailto:", "")
            name = str(a.params.get("CN", email))
            status = str(a.params.get("PARTSTAT", "NEEDS-ACTION"))
            if not any(p['email'] == email for p in participants):
                participants.append({
                    "email": email,
                    "name": name,
                    "role": "ATTENDEE",
                    "status": status
                })

    return participants


def get_calendar(teg_id):
    start = datetime.now(TEAM_TZ)
    end = start + timedelta(days=7)
    result = []
    client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
    principal = client.principal()
    for calendar in principal.calendars():
        try:
            events = calendar.date_search(start=start, end=end)
            for event in events:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    res = ''
                    if component.name == "VEVENT":
                        event_uid = str(component.get("uid"))
                        if component.get("uid") is None:
                            event_uid = str(component.get("dtstart"))

                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", "Нет описания"))
                        location = str(component.get("location", "Не указана"))

                        start_dt = component.get("dtstart").dt if component.get("dtstart") else "Неизвестно"
                        end_dt = component.get("dtend").dt if component.get("dtend") else "Неизвестно"

                        short_url = event_uid

                        if isinstance(start_dt, datetime):
                            start_dt_str = format_to_need_timezone(start_dt) if start_dt else "Неизвестно"
                        else:
                            start_dt_str = str(start_dt)

                        if isinstance(end_dt, datetime):
                            end_dt_str = format_to_need_timezone(end_dt) if end_dt else "Неизвестно"
                        else:
                            end_dt_str = str(end_dt)

                        res += (f'📅 *СОБЫТИЕ*\n'
                                f'{summary}\n'
                                f'{description}\n\n'
                                f'Локация: {location}\n\n'
                                f'Начало: {start_dt_str}\n'
                                f'Конец: {end_dt_str}\n\n')

                        attendees = get_all_participants(component)

                        if attendees:
                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)

                                if a['role'] == "ORGANIZER" and tg_id is not None:
                                    res += f"Организатор: [{name}](tg://user?id={tg_id})\n"
                                    break

                                elif a['role'] == "ORGANIZER" and tg_id is None:
                                    res += f"Организатор: {name}\n"
                                    break

                        if attendees:
                            res += "👥 Участники:\n"
                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)
                                if a['role'] != "ORGANIZER" and tg_id is not None:
                                    res += f"[{name}](tg://user?id={tg_id}) — {PARSTAT_RU.get(a['status'], 'Неизвестно')}\n"

                                elif a['role'] != "ORGANIZER" and tg_id is None:
                                    res += f"{name} — {PARSTAT_RU.get(a['status'], 'Неизвестно')}\n"

                        if attendees:
                            for user in attendees:
                                email = user.get('email')
                                if email is None:
                                    continue

                                tg_id = get_tg_id_by_email(email)
                                if tg_id == teg_id and res != '':
                                    markup = InlineKeyboardMarkup()
                                    if short_url is not None:
                                        accept = "success" if user['status'] == "ACCEPTED" else None
                                        decline = "success" if user['status'] == "DECLINED" else None
                                        maybe = "success" if user['status'] == "TENTATIVE" else None

                                        btn_accept = InlineKeyboardButton("Принять", style = accept,
                                                                          callback_data=f"cal_ACCEPTED_{short_url}_{user['status']}")
                                        btn_decline = InlineKeyboardButton("Отклонить", style = decline,
                                                                           callback_data=f"cal_DECLINED_{short_url}_{user['status']}")
                                        btn_maybe = InlineKeyboardButton("Под вопросом", style = maybe,
                                                                         callback_data=f"cal_TENTATIVE_{short_url}_{user['status']}")
                                        markup.row(btn_accept, btn_decline)

                                    result.append([res, markup])
                                    break


        except Exception as e:
            logger.error(f"CALDAV: {e}")
            return None

    return result


def update_event_partstat(event_uid: str, user_email: str, new_status: str) -> bool:
    """
        event_uid: UID события
        user_email: Email участника
        new_status: 'ACCEPTED', 'DECLINED', 'TENTATIVE'
    """
    try:
        start = datetime.now(TEAM_TZ)
        now_day = start.weekday()
        cooldown = COOLDOWN_DEFAULT
        if now_day == 3:
            cooldown = COOLDOWN_TUESDAY
        if now_day == 6:
            cooldown = COOLDOWN_SUNDAY

        end = start + timedelta(hours=cooldown)

        new_status = new_status.upper()
        if new_status not in ['ACCEPTED', 'DECLINED', 'TENTATIVE']:
            logger.error(f"Неверный статус: {new_status}")
            return False


        client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
        principal = client.principal()

        target_event = None

        calendars = principal.calendars()
        for calendar in calendars:
            try:
                events = calendar.date_search(start=start, end=end)
                for event in events:
                    ical = event.icalendar_instance
                    for component in ical.walk('VEVENT'):
                        if str(component.get('UID')) == event_uid:
                            target_event = event
                            logger.info(f"Событие найдено в календаре '{calendar.name}'")
                            break
                    if target_event: break
            except Exception as e:
                logger.debug(f"Пропуск календаря {calendar.name}: {e}")
                continue
            if target_event: break

        if not target_event:
            logger.error(f"Не удалось найти событие {event_uid} у пользователя {user_email}")
            return False

        ical = target_event.icalendar_instance
        updated = False

        for component in ical.walk('VEVENT'):
            if str(component.get('UID')) != event_uid:
                continue

            attendees = component.get('ATTENDEE')
            if not attendees: continue
            if not isinstance(attendees, list): attendees = [attendees]

            for attendee in attendees:
                if user_email.lower() in str(attendee).lower():
                    attendee.params['PARTSTAT'] = [vText(new_status)]
                    attendee.params['RSVP'] = [vText('FALSE')]
                    updated = True
                    break

        if updated:
            target_event.icalendar_instance = ical
            try:
                target_event.save()
                logger.info(f"Статус '{new_status}' успешно обновлен для {user_email}")
                return True
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}")
                return False
        else:
            logger.error(f"Участник {user_email} не найден в списке ATTENDEE.")
            return False

    except Exception as e:
        logger.exception(f"Критический сбой функции: {e}")
        return False

def poll_events():
    client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
    principal = client.principal()
    logger.info(f"CALDAV: Запускается фоновый опрос, частота {POLL_INTERVAL} секунд!")
    while True:
        logger.info(f"CALDAV: Получаю события...")

        start = datetime.now(TEAM_TZ)
        now_day = start.weekday()
        cooldown = COOLDOWN_DEFAULT
        if now_day == 3:
            cooldown = COOLDOWN_TUESDAY
        if now_day == 6:
            cooldown = COOLDOWN_SUNDAY

        end = start + timedelta(hours=cooldown)
        all_sended_events_uids = get_events_from_db()
        current_found_uids = set()

        for calendar in principal.calendars():
            try:
                events = calendar.date_search(start=start, end=end)
                for event in events:
                    cal = Calendar.from_ical(event.data)
                    event_url = str(event.url)

                    for component in cal.walk():
                        res = ''
                        if component.name == "VEVENT":
                            event_uid = str(component.get("uid"))
                            if component.get("uid") is None:
                                event_uid = str(component.get("dtstart"))

                            current_found_uids.add(event_uid)

                            if event_uid in all_sended_events_uids:
                                continue

                            all_sended_events_uids.add(event_uid)

                            save_event_sends(event_uid, event_url)

                            short_url = event_uid

                            summary = str(component.get("summary", "Без названия"))
                            description = str(component.get("description", "Нет описания"))
                            location = str(component.get("location", "Не указана"))

                            start_dt = component.get("dtstart").dt if component.get("dtstart") else "Неизвестно"
                            end_dt = component.get("dtend").dt if component.get("dtend") else "Неизвестно"

                            if isinstance(start_dt, datetime):
                                start_dt_str = format_to_need_timezone(start_dt) if start_dt else "Неизвестно"
                            else:
                                start_dt_str = str(start_dt)

                            if isinstance(end_dt, datetime):
                                end_dt_str = format_to_need_timezone(end_dt) if end_dt else "Неизвестно"
                            else:
                                end_dt_str = str(end_dt)

                            res += (f'📅 *СЕГОДНЯ СОБЫТИЕ*\n'
                                    f'{summary}\n'
                                    f'{description}\n\n'
                                    f'Локация: {location}\n\n'
                                    f'Начало: {start_dt_str}\n'
                                    f'Конец: {end_dt_str}\n\n')

                            attendees = get_all_participants(component)

                            if attendees:
                                for a in attendees:
                                    email = a.get('email')
                                    name = a.get('name')
                                    tg_id = get_tg_id_by_email(email)

                                    if a['role'] == "ORGANIZER" and tg_id is not None:
                                        res += f"Организатор: [{name}](tg://user?id={tg_id})\n"
                                        break

                                    elif a['role'] == "ORGANIZER" and tg_id is None:
                                        res += f"Организатор: {name}\n"
                                        break

                            if attendees:
                                res += "👥 Участники:\n"
                                for a in attendees:
                                    email = a.get('email')
                                    name = a.get('name')
                                    tg_id = get_tg_id_by_email(email)
                                    if a['role'] != "ORGANIZER" and tg_id is not None:
                                        res += f"[{name}](tg://user?id={tg_id}) — {PARSTAT_RU.get(a['status'], 'Неизвестно')}\n"

                                    elif a['role'] != "ORGANIZER" and tg_id is None:
                                        res += f"{name} — {PARSTAT_RU.get(a['status'], 'Неизвестно')}\n"

                            if attendees:

                                for user in attendees:
                                    email = user.get('email')
                                    if email is None:
                                        continue
                                    tg_id = get_tg_id_by_email(email)
                                    if tg_id:
                                        markup = InlineKeyboardMarkup()
                                        if short_url is not None:
                                            accept = "success" if user['status'] == "ACCEPTED" else None
                                            decline = "success" if user['status'] == "DECLINED" else None
                                            maybe = "success" if user['status'] == "TENTATIVE" else None

                                            btn_accept = InlineKeyboardButton("Принять", style=accept,
                                                                              callback_data=f"cal_ACCEPTED_{short_url}_{user['status']}")
                                            btn_decline = InlineKeyboardButton("Отклонить", style=decline,
                                                                               callback_data=f"cal_DECLINED_{short_url}_{user['status']}")
                                            btn_maybe = InlineKeyboardButton("Под вопросом", style=maybe,
                                                                             callback_data=f"cal_TENTATIVE_{short_url}_{user['status']}")

                                            markup.row(btn_accept, btn_decline)

                                        send_message_limited(tg_id, res, reply_markup=markup)

            except Exception as e:
                logger.exception(f"CALDAV: ой {e}")
        deleted_events_uids = all_sended_events_uids - current_found_uids
        for del_uid in deleted_events_uids:
            delete_event_sends(del_uid)
        sleep(POLL_INTERVAL)