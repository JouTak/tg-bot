from source.config import WEB_CALDAV_URL, USERNAME, PASSWORD
from source.db.repos.users import get_users
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