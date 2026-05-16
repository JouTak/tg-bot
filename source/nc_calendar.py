from source.config import WEB_CALDAV_URL, USERNAME, PASSWORD, COOLDOWN_TUESDAY, COOLDOWN_SUNDAY, COOLDOWN_DEFAULT, \
    POLL_INTERVAL
from source.connections.sender import send_message_limited
from source.db.repos.users import get_users, get_tg_id_by_email
from source.app_logging import logger
from source.db.repos.caldav_calendar import get_events_from_db, save_event_sends, delete_event_sends
from caldav import DAVClient
from icalendar import Calendar
from datetime import datetime, timedelta

from time import sleep

def parse_attendees(component):
    attendees = component.get("attendee")
    if not attendees:
        return []

    if not isinstance(attendees, list):
        attendees = [attendees]

    result = []

    for a in attendees:
        result.append({
            "email": a.to_ical().decode().replace("mailto:", ""),
            "name": a.params.get("CN"),
            "status": a.params.get("PARTSTAT"),   # ACCEPTED / DECLINED
            "role": a.params.get("ROLE"),         # REQ-PARTICIPANT
            "type": a.params.get("CUTYPE"),       # INDIVIDUAL / GROUP
            "rsvp": a.params.get("RSVP"),         # TRUE/FALSE
            "delegated_to": a.params.get("DELEGATED-TO"),
            "delegated_from": a.params.get("DELEGATED-FROM"),
        })

    return result


def get_calendar():
    start = datetime.now()
    end = start + timedelta(days=7)
    result = []
    client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
    principal = client.principal()
    #нужно просто получая всю инфу пройтись по attendes и мы просто отправить им сообщения
    #нужно по display name or email получать id и потом отправлять письмо счастья
    for calendar in principal.calendars():
        try:
            events = calendar.date_search(start=start, end=end)
            for event in events:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    res = ''
                    if component.name == "VEVENT":
                        #тут я получаю и у меня вся инфа мы смотрим такие ага и крч отправляем запрос
                        summary = str(component.get("summary", "Без названия"))
                        description = str(component.get("description", ""))
                        location = str(component.get("location", ""))
                        start_dt = component.get("dtstart").dt if component.get("dtstart") else None
                        end_dt = component.get("dtend").dt if component.get("dtend") else None
                        organizer = component.get("organizer")
                        res += f'📅 СОБЫТИЕ\nНазвание: {summary}\nОписание: {description}\nЛокация: {location}\nНачало: {start_dt}\nКонец: {end_dt}\nОрганизатор: {organizer}\n'

                        attendees = parse_attendees(component)

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

def poll_events():
    client = DAVClient(WEB_CALDAV_URL, username=USERNAME, password=PASSWORD)
    principal = client.principal()
    logger.info(f"CALDAV: Запускается фоновый опрос, частота {POLL_INTERVAL} секунд!")
    while True:
        start = datetime.now()

        now_day = start.weekday()
        if now_day == 3:
            cooldown = COOLDOWN_TUESDAY
        if now_day == 6:
            cooldown = COOLDOWN_SUNDAY
        else:
            cooldown = COOLDOWN_DEFAULT
        end = start + timedelta(hours=cooldown)
        all_sended_events = get_events_from_db()
        sended_events = set()
        events_now_sends = set()
        for calendar in principal.calendars():
            try:
                events = calendar.date_search(start=start, end=end)
                for event in events:
                    cal = Calendar.from_ical(event.data)
                    for component in cal.walk():
                        res = ''
                        if component.name == "VEVENT":

                            summary = str(component.get("summary", "Без названия"))
                            if summary in events_now_sends:
                                continue

                            if summary in all_sended_events:
                                sended_events.add(summary)
                                continue
                            else:
                                events_now_sends.add(summary)
                                save_event_sends(summary)

                            description = str(component.get("description", ""))
                            location = str(component.get("location", ""))
                            start_dt = component.get("dtstart").dt if component.get("dtstart") else None
                            end_dt = component.get("dtend").dt if component.get("dtend") else None
                            organizer = component.get("organizer")
                            res += f'📅 СОБЫТИЕ\nНазвание: {summary}\nОписание: {description}\nЛокация: {location}\nНачало: {start_dt}\nКонец: {end_dt}\nОрганизатор: {organizer}\n'

                            attendees = parse_attendees(component)

                            if attendees:
                                res += "👥 Участники:\n"
                                for a in attendees:
                                    res += f"{a}\n"

                            if attendees:
                                for user in attendees:
                                    email = user.get('email')
                                    if email is None:
                                        continue
                                    tg_id = get_tg_id_by_email(email)
                                    if tg_id:
                                        send_message_limited(tg_id, res)

            except Exception as e:
                logger.exception("CALDAV: ой")

        deleted_events_from_db = all_sended_events - sended_events
        for del_event in deleted_events_from_db:
            delete_event_sends(del_event)

        sleep(POLL_INTERVAL)