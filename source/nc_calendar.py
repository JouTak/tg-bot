from source.config import WEB_CALDAV_URL, USERNAME, PASSWORD, COOLDOWN_TUESDAY, COOLDOWN_SUNDAY, COOLDOWN_DEFAULT, \
    POLL_INTERVAL, WEB_APP_URL, UPDATE_INTERVAL, TIMEZONE, CALDAV_USERNAME, CALDAV_PASSWORD, CALDAV_COOLDOWNS
from source.connections.sender import send_message_limited
from source.db.repos.users import (
    NEXTCLOUD_FIELD_MISSING, get_tg_id_by_email, get_timezone,
    update_nextcloud_profile,
)
from source.app_logging import logger
from source.db.repos.caldav_calendar import (
    get_events_from_db, save_event_sends, delete_event_sends, get_id_by_name,
)
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from caldav import DAVClient, error
from icalendar import Calendar, vText
from datetime import datetime, timedelta, timezone, time, date

from time import sleep
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

try:
    TEAM_TZ = ZoneInfo(TIMEZONE)
except Exception:
    TEAM_TZ = timezone(timedelta(hours=3))


def _localize_ical_property(prop, target_timezone):
    """Разрешает aware, TZID, floating и all-day значения для получателя."""
    if prop is None:
        return None
    value = prop.dt
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is not None:
        return value.astimezone(target_timezone)
    source_tzid = prop.params.get("TZID")
    if source_tzid:
        value = value.replace(tzinfo=ZoneInfo(str(source_tzid)))
        return value.astimezone(target_timezone)
    return value.replace(tzinfo=target_timezone)


def _as_datetime(value, target_timezone):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, target_timezone)
    return None


def _format_event_time(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value) if value is not None else "Неизвестно"


def _local_window(target_timezone, days):
    today = datetime.now(timezone.utc).astimezone(target_timezone).date()
    start = datetime.combine(today, time.min, target_timezone)
    return start, start + timedelta(days=days)

PARSTAT_RU = {
    "ACCEPTED": "Будет",
    "DECLINED": "Не будет",
    "TENTATIVE": "Под вопросом",
    "NEEDS-ACTION": "Неизвестно"
}

WEEKDAY_RU = {
    0: " ПОНЕДЕЛЬНИК",
    1: "О ВТОРНИК",
    2: " СРЕДУ",
    3: " ЧЕТВЕРГ",
    4: " ПЯТНИЦУ",
    5: " СУББОТУ",
    6: " ВОСКРЕСЕНЬЕ",
    None: " ОПРЕДЕЛЕННЫЙ ДЕНЬ"
}

def msg_design_from_button(uid: str, teg_id: int, type_msg: int):
    tz_user = get_timezone(teg_id)
    start, end = _local_window(tz_user, 7)
    client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
    principal = client.principal()
    res = ''
    status = ''
    for calendar in principal.calendars():
        try:
            events = calendar.date_search(start=start, end=end, expand=True)
            for event in events:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    if component.name == "VEVENT" and uid == str(component.get("uid")):
                        if component.get("dtstart") is None:
                            continue
                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", "Нет описания"))
                        location = str(component.get("location", "Не указана"))

                        start_dt = _localize_ical_property(component.get("dtstart"), tz_user)
                        end_dt = _localize_ical_property(component.get("dtend"), tz_user)
                        start_dt_str = _format_event_time(start_dt)
                        end_dt_str = _format_event_time(end_dt)
                        weekday = start_dt.weekday() if isinstance(start_dt, (datetime, date)) else None

                        if type_msg == 2:
                            res += (f'📅 **СЕГОДНЯ СОБЫТИЕ В{WEEKDAY_RU.get(weekday, "ОПРЕДЕЛЕННЫЙ ДЕНЬ")}**<br>\n'
                                    f'{summary}<br>\n'
                                    f'{description}<br>\n\n'
                                    f'Локация: {location}<br>\n\n'
                                    f'Начало: {start_dt_str}<br>\n'
                                    f'Конец: {end_dt_str}<br>\n\n')
                        else:
                            res += (f'📅 **СОБЫТИЕ В{WEEKDAY_RU.get(weekday, "ОПРЕДЕЛЕННЫЙ ДЕНЬ")}<br>**\n'
                                    f'{summary}<br>\n'
                                    f'{description}<br>\n\n'
                                    f'Локация: {location}<br>\n\n'
                                    f'Начало: {start_dt_str}<br>\n'
                                    f'Конец: {end_dt_str}<br>\n\n')

                        attendees = get_all_participants(component)

                        if attendees:
                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)

                                if a['role'] == "ORGANIZER" and tg_id is not None:
                                    res += f"Организатор: <a href='tg://user?id={tg_id}'>{name}</a><br>\n"
                                    break

                                elif a['role'] == "ORGANIZER" and tg_id is None:
                                    res += f"Организатор: {name}<br>\n"
                                    break

                            res += "👥 Участники:<br>\n<blockquote expandable><br>\n"
                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)
                                if a['role'] != "ORGANIZER" and tg_id is not None and tg_id == teg_id:
                                    status = a['status']
                                    res += f"<a href='tg://user?id={tg_id}'>{name}</a> — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"
                                    break

                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)
                                if a['role'] != "ORGANIZER" and tg_id is not None and tg_id != teg_id:
                                    res += f"<a href='tg://user?id={tg_id}'>{name}</a> — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"

                                elif a['role'] != "ORGANIZER" and tg_id is None:
                                    res += f"{name} — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"

                            if res[-1] == '\n': res = res[:-1]
                            res += '</blockquote>'

                        return [res, status]

        except Exception as e:
            logger.error(f"CALDAV: {e}")
            return None, None


def cleanup_uid(target_uid: str):
    """
    Оставляет только мастер-событие (RECURRENCE-ID=None)
    для указанного UID.
    """
    start = datetime.now(TEAM_TZ)
    end = start + timedelta(days=6)
    client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
    principal = client.principal()
    for calendar in principal.calendars():
        try:
            events = calendar.date_search(start=start, end=end)
            for event in events:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        vevents = [
                            c for c in cal.subcomponents
                            if getattr(c, "name", None) == "VEVENT"
                        ]

                        target_vevents = [
                            v for v in vevents
                            if str(v.get("UID")) == target_uid
                        ]

                        if not target_vevents:
                            continue

                        print(f"\nНайден UID={target_uid}")
                        print(f"URL: {event.url}")
                        print(f"VEVENT до очистки: {len(target_vevents)}")

                        master = None

                        for v in target_vevents:
                            if v.get("RECURRENCE-ID") is None:
                                master = v
                                break

                        if master is None:
                            print("Мастер-событие не найдено!")
                            return False

                        new_cal = Calendar()
                        for k, v in cal.items():
                            new_cal.add(k, v)
                        for component in cal.subcomponents:
                            if getattr(component, "name", None) != "VEVENT":
                                new_cal.add_component(component)

                        new_cal.add_component(master)

                        event.data = new_cal.to_ical()
                        event.save()
        except Exception as e:
            print(e)

def format_to_timezone(dt: datetime, tz) -> str:
    """Преобразует datetime в timezone пользователя и возвращает время ЧЧ:ММ."""
    if not isinstance(dt, datetime):
        return str(dt)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(tz).strftime("%H:%M")

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
                    email = user_data['email'] if 'email' in user_data else NEXTCLOUD_FIELD_MISSING
                    timezone_value = (
                        user_data['timezone']
                        if 'timezone' in user_data
                        else NEXTCLOUD_FIELD_MISSING
                    )
                    if update_nextcloud_profile(
                            uid, email=email, timezone_value=timezone_value):
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


def get_calendar(teg_id, cooldown=6, all_events=False):
    tz_user = get_timezone(teg_id)
    now_local = datetime.now(timezone.utc).astimezone(tz_user)
    if cooldown == 1:
        start, end = _local_window(tz_user, 1)
    elif cooldown in (6, 7):
        start, end = _local_window(tz_user, 7)
    else:
        start = now_local
        end = start + timedelta(days=cooldown)

    result = []
    client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
    principal = client.principal()
    for calendar in principal.calendars():
        try:
            events = calendar.date_search(start=start, end=end, expand=True)
            for event in events:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    res = ''
                    if component.name == "VEVENT":
                        start_property = component.get("dtstart")
                        if start_property is None:
                            continue
                        event_uid = str(component.get("uid"))
                        if component.get("uid") is None:
                            event_uid = str(component.get("dtstart"))

                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", "Нет описания"))
                        location = str(component.get("location", "Не указана"))

                        start_dt = _localize_ical_property(start_property, tz_user)
                        end_dt = _localize_ical_property(component.get("dtend"), tz_user)
                        start_for_window = _as_datetime(start_dt, tz_user)
                        if start_for_window is None or not (start <= start_for_window < end):
                            continue

                        short_url = event_uid

                        start_dt_str = _format_event_time(start_dt)
                        end_dt_str = _format_event_time(end_dt)

                        res += (f'📅 **СОБЫТИЕ В{WEEKDAY_RU.get(start_dt.weekday(), "ОПРЕДЕЛЕННЫЙ ДЕНЬ")}**<br>\n'
                                f'{summary}<br>\n'
                                f'{description}<br>\n\n'                                
                                f'Локация: {location}<br>\n\n'
                                f'Начало: {start_dt_str}<br>\n'
                                f'Конец: {end_dt_str}<br>\n\n')

                        attendees = get_all_participants(component)

                        if attendees:
                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)

                                if a['role'] == "ORGANIZER" and tg_id is not None:
                                    res += f"Организатор: <a href='tg://user?id={tg_id}'>{name}</a><br>\n"
                                    break

                                elif a['role'] == "ORGANIZER" and tg_id is None:
                                    res += f"Организатор: {name}<br>\n"
                                    break

                            res += "👥 Участники:<br>\n<blockquote expandable><br>\n"

                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)
                                if a['role'] != "ORGANIZER" and tg_id is not None and teg_id == tg_id:
                                    res += f"<a href='tg://user?id={tg_id}'>{name}</a> — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"
                                    break

                            for a in attendees:
                                email = a.get('email')
                                name = a.get('name')
                                tg_id = get_tg_id_by_email(email)
                                if a['role'] != "ORGANIZER" and tg_id is not None and teg_id != tg_id:
                                    res += f"<a href='tg://user?id={tg_id}'>{name}</a> — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"

                                elif a['role'] != "ORGANIZER" and tg_id is None:
                                    res += f"{name} — {PARSTAT_RU.get(a['status'], 'Неизвестно')}<br>\n"

                            if res[-1] == '\n': res = res[:-1]
                            res += '</blockquote>'

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
                                        decline = "danger" if user['status'] == "DECLINED" else None
                                        maybe = "success" if user['status'] == "TENTATIVE" else None

                                        btn_accept = InlineKeyboardButton("Принять", style = accept,
                                                                          callback_data=f"c_ACCEPTED_{short_url}_{user['status']}_1")
                                        btn_decline = InlineKeyboardButton("Отклонить", style = decline,
                                                                           callback_data=f"c_DECLINED_{short_url}_{user['status']}_1")
                                        btn_maybe = InlineKeyboardButton("Под вопросом", style = maybe,
                                                                         callback_data=f"c_TENTATIVE_{short_url}_{user['status']}_1")
                                        btn_update = InlineKeyboardButton("🔄",
                                                                          callback_data=f"update_{short_url}_1")
                                        if user['role'] != "ORGANIZER":
                                            markup.row(btn_accept, btn_update, btn_decline)
                                        else:
                                            markup.row(btn_update)

                                    result.append((start_for_window, [res, markup]))
                                    break

                                elif all_events:
                                    result.append((start_for_window, [res, None]))
                                    break


        except Exception as e:
            logger.error(f"CALDAV: {e}")
            return None

    def get_sort_key(item):
        dt = item[0]
        if isinstance(dt, datetime):
            return dt.timestamp()
        return float('inf')

    result.sort(key=get_sort_key)

    final_result = [item[1] for item in result]

    return final_result


def update_event_partstat(event_uid: str, user_email: str, new_status: str) -> bool:
    """
        event_uid: UID события
        user_email: Email участника
        new_status: 'ACCEPTED', 'DECLINED', 'TENTATIVE'
    """
    try:
        start = datetime.now(TEAM_TZ)
        end = start + timedelta(days=6)

        new_status = new_status.upper()
        if new_status not in ['ACCEPTED', 'DECLINED', 'TENTATIVE']:
            logger.error(f"Неверный статус: {new_status}")
            return False


        client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
        principal = client.principal()

        target_event = None

        calendars = principal.calendars()
        for calendar in calendars:
            try:
                events = calendar.date_search(start=start, end=end, expand=True)
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


def set_all_attendees_needs_action(event_uid: str) -> bool:
    """
    Устанавливает статус NEEDS-ACTION (Ожидает решения)
    для всех участников (ATTENDEE) указанного события.

    event_uid: UID события
    """
    try:
        start = datetime.now(TEAM_TZ)
        end = start + timedelta(days=7)

        client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
        principal = client.principal()

        target_event = None

        calendars = principal.calendars()
        for calendar in calendars:
            try:
                events = calendar.date_search(start=start, end=end, expand=True)
                for event in events:
                    ical = event.icalendar_instance
                    for component in ical.walk('VEVENT'):
                        if str(component.get('UID')) == event_uid:
                            target_event = event
                            start_property = component.get('dtstart')
                            start_value = start_property.dt if start_property else "без DTSTART"
                            logger.info(f"Событие найдено в календаре '{calendar.name}', {component.get('summary')} {start_value}")
                            break
                    if target_event: break
            except Exception as e:
                logger.debug(f"Пропуск календаря {calendar.name}: {e}")
                continue
            if target_event: break

        if not target_event:
            logger.error(f"Не удалось найти событие {event_uid} для сброса статусов")
            return False

        ical = target_event.icalendar_instance
        updated = False

        for component in ical.walk('VEVENT'):
            if str(component.get('UID')) != event_uid:
                continue

            attendees = component.get('ATTENDEE')
            if not attendees:
                continue

            if not isinstance(attendees, list):
                attendees = [attendees]

            for attendee in attendees:
                attendee.params['PARTSTAT'] = [vText('NEEDS-ACTION')]
                attendee.params['RSVP'] = [vText('TRUE')]
                updated = True

        if updated:
            target_event.icalendar_instance = ical
            try:
                target_event.save()
                logger.info(f"Статус 'NEEDS-ACTION' успешно установлен для всех участников события {event_uid}")
                return True
            except Exception as e:
                logger.error(f"Ошибка сохранения события {event_uid}: {e}")
                return False
        else:
            logger.warning(f"У события {event_uid} нет списка участников (ATTENDEE). Изменять нечего.")
            return False

    except Exception as e:
        logger.exception(f"Критический сбой функции set_all_attendees_needs_action: {e}")
        return False

def poll_events():
    client = DAVClient(WEB_CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD)
    principal = client.principal()
    logger.info(f"CALDAV: Запускается фоновый опрос, частота {POLL_INTERVAL} секунд!")
    while True:
        logger.info(f"CALDAV: Получаю события...")

        now_utc = datetime.now(timezone.utc)
        largest_cooldown = max(
            (value for values in CALDAV_COOLDOWNS.values() for value in values),
            default=24 * 60,
        )
        end_utc = now_utc + timedelta(minutes=max(24 * 60, largest_cooldown))
        saved_event_keys = get_events_from_db()
        observed_event_keys = set()
        scan_complete = True

        try:
            calendars = principal.calendars()
        except Exception as e:
            logger.error(f"CALDAV: Ошибка получения календарей: {e}")
            sleep(POLL_INTERVAL)
            continue

        for calendar in calendars:
            try:
                # Expanded occurrences безопасны для чтения и не сохраняются обратно.
                events = calendar.date_search(start=now_utc, end=end_utc, expand=True)
            except Exception as e:
                logger.error(f"CALDAV: Ошибка поиска событий в календаре: {e}")
                scan_complete = False
                continue

            for event in events:
                try:
                    cal = Calendar.from_ical(event.data)
                    event_url = str(event.url)

                    for component in cal.walk():
                        if component.name != "VEVENT":
                            continue
                        start_property = component.get("dtstart")
                        if start_property is None:
                            scan_complete = False
                            continue
                        if not isinstance(start_property.dt, datetime):
                            continue

                        if component.get("status") == "CANCELLED":
                            continue

                        event_uid = str(component.get("uid") or start_property)
                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", "Нет описания"))
                        location = str(component.get("location", "Не указана"))
                        cooldowns = next(
                            (values for prefix, values in CALDAV_COOLDOWNS.items()
                             if summary.startswith(prefix)),
                            [],
                        )
                        if not cooldowns:
                            continue

                        attendees = get_all_participants(component)
                        for user in attendees:
                            teg_id = get_tg_id_by_email(user.get('email'))
                            if teg_id is None:
                                continue
                            try:
                                tz_user = get_timezone(teg_id)
                                start_dt = _localize_ical_property(start_property, tz_user)
                                end_dt = _localize_ical_property(component.get("dtend"), tz_user)
                            except (OSError, ValueError, ZoneInfoNotFoundError) as e:
                                scan_complete = False
                                logger.error(f"CALDAV: Неизвестный TZID у события {event_uid}: {e}")
                                continue

                            start_instant = _as_datetime(start_dt, tz_user)
                            if start_instant is None:
                                scan_complete = False
                                continue
                            until_start = start_instant.astimezone(timezone.utc) - now_utc
                            if not timedelta() <= until_start <= timedelta(minutes=max(cooldowns)):
                                continue

                            keys = [(teg_id, cooldown, event_uid) for cooldown in cooldowns]
                            observed_event_keys.update(keys)

                            pending_key = None
                            poll_delta = timedelta(seconds=POLL_INTERVAL)
                            for key in sorted(keys, key=lambda x: x[1], reverse=True):
                                if key in saved_event_keys:
                                    continue

                                cooldown_delta = timedelta(minutes=key[1])

                                if cooldown_delta - poll_delta <= until_start <= cooldown_delta:
                                    pending_key = key
                                    break

                            if pending_key is None:
                                continue

                            res = (f'📅 **СЕГОДНЯ СОБЫТИЕ В{WEEKDAY_RU.get(start_dt.weekday(), "ОПРЕДЕЛЕННЫЙ ДЕНЬ")}**<br>\n'
                                   f'{summary}\n{description}<br>\n\n'
                                   f'Локация: {location}<br>\n\n'
                                   f'Начало: {_format_event_time(start_dt)}<br>\n'
                                   f'Конец: {_format_event_time(end_dt)}<br>\n\n')

                            name_for_send = user.get('name', '')
                            for participant in attendees:
                                participant_id = get_tg_id_by_email(participant.get('email'))
                                name = participant.get('name')
                                if participant['role'] == "ORGANIZER":
                                    if participant_id is not None:
                                        res += f"Организатор: <a href='tg://user?id={participant_id}'>{name}</a><br>\n"
                                    else:
                                        res += f"Организатор: {name}<br>\n"
                                    break

                            res += "👥 Участники:<br>\n<blockquote expandable><br>\n"
                            ordered_attendees = sorted(
                                (a for a in attendees if a['role'] != "ORGANIZER"),
                                key=lambda a: get_tg_id_by_email(a.get('email')) != teg_id,
                            )
                            second_send = False

                            for participant in ordered_attendees:
                                participant_id = get_tg_id_by_email(participant.get('email'))
                                name = participant.get('name')
                                status = PARSTAT_RU.get(participant['status'], 'Неизвестно')

                                if participant_id == teg_id and participant['status'] == "ACCEPTED":
                                    res = f"Напоминаю, что созвон **{summary}** в **{_format_event_time(start_dt)}**!"
                                    second_send = True
                                    break

                                if participant_id is not None:
                                    res += f"<a href='tg://user?id={participant_id}'>{name}</a> — {status}<br>\n"
                                else:
                                    res += f"{name} — {status}<br>\n"
                            if res[-1] == '\n':
                                res = res[:-1]

                            if not second_send:
                                res += '</blockquote>'

                            markup = InlineKeyboardMarkup()
                            accept = "success" if user['status'] == "ACCEPTED" else None
                            decline = "danger" if user['status'] == "DECLINED" else None
                            maybe = "success" if user['status'] == "TENTATIVE" else None
                            btn_accept = InlineKeyboardButton(
                                "Принять", style=accept,
                                callback_data=f"c_ACCEPTED_{event_uid}_{user['status']}_2")
                            btn_decline = InlineKeyboardButton(
                                "Отклонить", style=decline,
                                callback_data=f"c_DECLINED_{event_uid}_{user['status']}_2")
                            btn_maybe = InlineKeyboardButton(
                                "Под вопросом", style=maybe,
                                callback_data=f"c_TENTATIVE_{event_uid}_{user['status']}_2")
                            btn_update = InlineKeyboardButton(
                                "🔄", callback_data=f"update_{event_uid}_2")
                            if user['role'] != "ORGANIZER":
                                markup.row(btn_accept, btn_update, btn_decline)
                            else:
                                markup.row(btn_update)
                            send_message_limited(teg_id, res, reply_markup=markup)
                            save_event_sends(
                                name_for_send, teg_id, pending_key[1], event_uid, event_url
                            )
                            saved_event_keys.add(pending_key)

                except Exception as e:
                    scan_complete = False
                    logger.exception(f"CALDAV: ой {e}")

        if scan_complete:
            for tg_id, cooldown, event_uid in saved_event_keys - observed_event_keys:
                try:
                    delete_event_sends(tg_id, cooldown, event_uid)
                except Exception as e:
                    logger.error(f"CALDAV: Ошибка удаления события из БД: {e}")

        sleep(POLL_INTERVAL)
