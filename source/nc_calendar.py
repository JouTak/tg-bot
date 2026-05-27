from source.config import WEB_CALDAV_URL, USERNAME, PASSWORD, COOLDOWN_TUESDAY, COOLDOWN_SUNDAY, COOLDOWN_DEFAULT, \
    POLL_INTERVAL
from source.connections.sender import send_message_limited
from source.db.repos.users import get_users, get_tg_id_by_email
from source.app_logging import logger
from source.db.repos.caldav_calendar import get_events_from_db, save_event_sends, delete_event_sends, get_id_by_name
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from caldav import DAVClient, error
from icalendar import Calendar
from datetime import datetime, timedelta

from time import sleep


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


def get_calendar():
    start = datetime.now()
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
                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", ""))
                        location = str(component.get("location", ""))
                        start_dt = component.get("dtstart").dt if component.get("dtstart") else None
                        end_dt = component.get("dtend").dt if component.get("dtend") else None
                        organizer = component.get("organizer")
                        res += f'📅 СОБЫТИЕ\nНазвание: {summary}\nОписание: {description}\nЛокация: {location}\nНачало: {start_dt}\nКонец: {end_dt}\nОрганизатор: {organizer}\n'

                        attendees = get_all_participants(component)

                        if attendees:
                            res += "👥 Участники:\n"
                            for a in attendees:
                                res += f"{a}\n"

                        # 🔥 ВСЯ СЫРАЯ ИНФА (очень полезно)
                        print("\n--- RAW FIELDS ---")
                        for k, v in component.items():
                            print(k, ":", v)

                    if res != '':
                        result.append(res)

        except Exception as e:
            return None

    return result


def update_event_partstat(url: str, user_email: str, new_status: str) -> bool:
    try:
        client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
        caldav_event = client.calendar(url=url).event_by_url(url)

        if caldav_event:
            cal = Calendar.from_ical(caldav_event.data)
            updated = False

            for component in cal.walk():
                if component.name == "VEVENT":
                    attendees = component.get('attendee', [])
                    if not isinstance(attendees, list):
                        attendees = [attendees]

                    for attendee in attendees:
                        if user_email.lower() in str(attendee).lower():
                            attendee.params['PARTSTAT'] = [new_status]
                            updated = True
                            break

            if updated:
                caldav_event.data = cal.to_ical()
                caldav_event.save()
                return True

        return False

    except Exception as e:
        logger.exception(f"Ошибка при обновлении статуса в CalDAV: {e}")
        return False


def poll_events():
    client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
    principal = client.principal()
    logger.info(f"CALDAV: Запускается фоновый опрос, частота {POLL_INTERVAL} секунд!")
    while True:
        logger.info(f"CALDAV: Получаю события...")
        start = datetime.now()

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
                            current_found_uids.add(event_uid)

                            if event_uid in all_sended_events_uids:
                                continue

                            all_sended_events_uids.add(event_uid)

                            save_event_sends(event_uid, event_url)

                            short_url = get_id_by_name(event_uid)

                            summary = str(component.get("summary", "Без названия"))
                            description = str(component.get("description", "Нет описания"))
                            location = str(component.get("location", "Не указана"))

                            start_dt = component.get("dtstart").dt if component.get("dtstart") else "Неизвестно"
                            end_dt = component.get("dtend").dt if component.get("dtend") else "Неизвестно"

                            if isinstance(start_dt, datetime):
                                start_dt_str = start_dt.strftime("%H:%M")
                            else:
                                start_dt_str = str(start_dt)

                            if isinstance(end_dt, datetime):
                                end_dt_str = end_dt.strftime("%H:%M")
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
                                    if a['role'] == "ORGANIZER":
                                        res += f"Организатор: [{name}](tg://user?id={tg_id})\n"
                                        break

                            if attendees:
                                res += "👥 Участники:\n"
                                for a in attendees:
                                    email = a.get('email')
                                    name = a.get('name')
                                    tg_id = get_tg_id_by_email(email)
                                    if a['role'] != "ORGANIZER":
                                        res += f"[{name}](tg://user?id={tg_id})\n"

                            if attendees:

                                for user in attendees:
                                    email = user.get('email')
                                    if email is None:
                                        continue
                                    tg_id = get_tg_id_by_email(email)
                                    if tg_id:
                                        markup = InlineKeyboardMarkup()
                                        btn_accept = InlineKeyboardButton("Принять",
                                                                          callback_data=f"cal_ACCEPTED_{short_url}")
                                        btn_decline = InlineKeyboardButton("Отклонить",
                                                                           callback_data=f"cal_DECLINED_{short_url}")
                                        btn_maybe = InlineKeyboardButton("Под вопросом", callback_data=f"cal_TENTATIVE_{short_url}")
                                        markup.row(btn_accept, btn_decline)
                                        send_message_limited(tg_id, res, reply_markup=markup)

            except Exception as e:
                logger.exception("CALDAV: ой")
        deleted_events_uids = all_sended_events_uids - current_found_uids
        for del_uid in deleted_events_uids:
            delete_event_sends(del_uid)
        sleep(POLL_INTERVAL)