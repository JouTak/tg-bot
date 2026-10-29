from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from icalendar import vText


def localize_ical_property(prop, target_timezone):
    """Resolve aware, TZID, floating and all-day iCalendar values."""
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


def _ical_value_key(prop):
    if prop is None:
        return None
    value = localize_ical_property(prop, timezone.utc)
    if isinstance(value, datetime):
        return 'datetime', value.astimezone(timezone.utc)
    if isinstance(value, date):
        return 'date', value
    return 'value', str(value)


def find_event_component(ical, event_uid, recurrence_id=None):
    recurrence_key = _ical_value_key(recurrence_id)
    for component in ical.walk('VEVENT'):
        if str(component.get('UID')) != event_uid:
            continue
        component_recurrence = component.get('RECURRENCE-ID')
        if recurrence_id is None and component_recurrence is None:
            return component
        if recurrence_key == _ical_value_key(component_recurrence):
            return component
    return None


def select_response_component(ical, event_uid, recurrence_id=None):
    """Match Nextcloud Calendar's RSVP scope for recurring events.

    Server-expanded occurrences carry a RECURRENCE-ID even when the stored
    calendar object contains only the recurring master. In that case the web
    Calendar updates the master (the whole series) instead of creating a new
    exception. An already stored exception remains occurrence-scoped.
    """
    if recurrence_id is not None:
        occurrence = find_event_component(ical, event_uid, recurrence_id)
        if occurrence is not None:
            return occurrence, 'occurrence'

    master = find_event_component(ical, event_uid)
    if master is not None:
        return master, 'series'
    return None, None


def attendee_status(component, user_email: str):
    if component is None:
        return None
    attendees = component.get('ATTENDEE')
    if attendees is None:
        return None
    if not isinstance(attendees, list):
        attendees = [attendees]
    normalized_email = user_email.strip().lower()
    for attendee in attendees:
        email = str(attendee).strip().lower().removeprefix('mailto:')
        if email == normalized_email:
            return str(attendee.params.get('PARTSTAT', 'NEEDS-ACTION')).upper()
    return None


def set_attendee_partstat(component, user_email: str, new_status: str) -> bool:
    attendees = component.get('ATTENDEE') if component is not None else None
    if attendees is None:
        return False
    if not isinstance(attendees, list):
        attendees = [attendees]
    normalized_email = user_email.strip().lower()
    for attendee in attendees:
        email = str(attendee).strip().lower().removeprefix('mailto:')
        if email == normalized_email:
            attendee.params['PARTSTAT'] = vText(new_status)
            return True
    return False
