import os
import unittest
from unittest.mock import Mock, patch

from icalendar import Calendar

os.environ.setdefault('BOT_TOKEN', '123456:abcdefghijklmnopqrstuvwxyzABCDE')
os.environ.setdefault('BASE_URL', 'https://example.invalid')
os.environ.setdefault('NEXTCLOUD_USER', 'calendar')
os.environ.setdefault('NEXTCLOUD_PASS', 'secret')
os.environ.setdefault('MYSQL_USER', 'test')
os.environ.setdefault('MYSQL_PASS', 'test')
os.environ.setdefault('MYSQL_DB', 'test')
os.environ.setdefault('WEB_CALDAV_URL', 'https://example.invalid/remote.php/dav')

from source.caldav_rsvp import (  # noqa: E402
    attendee_status,
    select_response_component,
    set_attendee_partstat,
)
from source import nc_calendar  # noqa: E402


MASTER_ICS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//JouTak test//EN\r
BEGIN:VEVENT\r
UID:sync-event\r
DTSTART;TZID=Europe/Moscow:20261029T220000\r
DTEND;TZID=Europe/Moscow:20261029T230000\r
RRULE:FREQ=WEEKLY;BYDAY=TH\r
ORGANIZER:mailto:calendar@example.com\r
ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:user@example.com\r
END:VEVENT\r
END:VCALENDAR\r
"""

EXPANDED_ICS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//JouTak test//EN\r
BEGIN:VEVENT\r
UID:sync-event\r
RECURRENCE-ID;TZID=Europe/Moscow:20261029T220000\r
DTSTART;TZID=Europe/Moscow:20261029T220000\r
DTEND;TZID=Europe/Moscow:20261029T230000\r
ORGANIZER:mailto:calendar@example.com\r
ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:user@example.com\r
END:VEVENT\r
END:VCALENDAR\r
"""

EXCEPTION_ICS = MASTER_ICS.replace(
    b"END:VCALENDAR\r\n",
    b"""BEGIN:VEVENT\r
UID:sync-event\r
RECURRENCE-ID;TZID=Europe/Moscow:20261105T220000\r
DTSTART;TZID=Europe/Moscow:20261105T223000\r
DTEND;TZID=Europe/Moscow:20261105T233000\r
ORGANIZER:mailto:calendar@example.com\r
ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:user@example.com\r
END:VEVENT\r
END:VCALENDAR\r
""",
)


class CalDavRsvpSelectionTests(unittest.TestCase):
    def test_generated_occurrence_updates_master_without_adding_exception(self):
        stored = Calendar.from_ical(MASTER_ICS)
        expanded = Calendar.from_ical(EXPANDED_ICS)
        recurrence_id = expanded.walk('VEVENT')[0].get('RECURRENCE-ID')
        original_count = len(stored.walk('VEVENT'))

        component, scope = select_response_component(
            stored, 'sync-event', recurrence_id
        )
        self.assertEqual(scope, 'series')
        self.assertIsNone(component.get('RECURRENCE-ID'))
        self.assertTrue(set_attendee_partstat(
            component, 'user@example.com', 'ACCEPTED'
        ))
        self.assertEqual(len(stored.walk('VEVENT')), original_count)
        self.assertEqual(
            attendee_status(component, 'user@example.com'), 'ACCEPTED'
        )
        attendee = component.get('ATTENDEE')
        self.assertEqual(str(attendee.params['RSVP']).upper(), 'TRUE')

    def test_existing_exception_remains_occurrence_scoped(self):
        stored = Calendar.from_ical(EXCEPTION_ICS)
        exceptions = [
            component for component in stored.walk('VEVENT')
            if component.get('RECURRENCE-ID') is not None
        ]
        recurrence_id = exceptions[0].get('RECURRENCE-ID')

        component, scope = select_response_component(
            stored, 'sync-event', recurrence_id
        )
        self.assertEqual(scope, 'occurrence')
        self.assertIs(component, exceptions[0])


class CalDavRsvpRequestTests(unittest.TestCase):
    def _configure_client(self, dav_client_cls, get_credentials, etag):
        get_credentials.return_value = ('user', 'token')

        expanded_event = Mock()
        expanded_event.icalendar_instance = Calendar.from_ical(EXPANDED_ICS)

        raw_event = Mock()
        raw_event.icalendar_instance = Calendar.from_ical(MASTER_ICS)
        raw_event.get_property.return_value = etag
        raw_event.url = 'https://example.invalid/calendars/user/sync.ics'

        calendar = Mock()
        calendar.url = 'https://example.invalid/calendars/user/personal/'
        calendar.name = 'Personal'
        calendar.date_search.return_value = [expanded_event]
        calendar.search.return_value = [raw_event]

        principal = Mock()
        principal.calendars.return_value = [calendar]
        client = Mock()
        client.principal.return_value = principal
        dav_client_cls.return_value = client
        return client, calendar, raw_event

    @patch.object(nc_calendar, 'get_user_credentials_from_db')
    @patch.object(nc_calendar, 'DAVClient')
    def test_update_matches_cloud_payload_and_uses_report_etag(
            self, dav_client_cls, get_credentials):
        client, calendar, raw_event = self._configure_client(
            dav_client_cls, get_credentials, '"etag-from-report"'
        )
        client.put.return_value = Mock(status=204)

        self.assertTrue(nc_calendar.update_event_partstat(
            'sync-event', 'user@example.com', 'ACCEPTED'
        ))

        calendar.search.assert_called_once()
        raw_event.get_property.assert_called_once()
        etag_property = raw_event.get_property.call_args.args[0]
        self.assertIsInstance(etag_property, nc_calendar.dav.GetEtag)
        self.assertEqual(
            raw_event.get_property.call_args.kwargs, {'use_cached': True}
        )
        _, body, headers = client.put.call_args.args
        saved = Calendar.from_ical(body)
        components = saved.walk('VEVENT')
        self.assertEqual(len(components), 1)
        self.assertIsNone(components[0].get('RECURRENCE-ID'))
        self.assertEqual(
            attendee_status(components[0], 'user@example.com'), 'ACCEPTED'
        )
        self.assertEqual(headers['If-Match'], '"etag-from-report"')

    @patch.object(nc_calendar, 'get_user_credentials_from_db')
    @patch.object(nc_calendar, 'DAVClient')
    def test_update_does_not_fall_back_to_an_unconditional_put(
            self, dav_client_cls, get_credentials):
        client, _, raw_event = self._configure_client(
            dav_client_cls, get_credentials, '"etag-from-report"'
        )
        client.put.return_value = Mock(status=412)
        client.request.return_value = Mock(status=200, raw=MASTER_ICS)

        self.assertFalse(nc_calendar.update_event_partstat(
            'sync-event', 'user@example.com', 'ACCEPTED'
        ))

        client.put.assert_called_once()
        client.request.assert_called_once_with(raw_event.url, 'GET')


if __name__ == '__main__':
    unittest.main()
