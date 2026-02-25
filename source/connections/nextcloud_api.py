import time
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Any

import requests
import socket, http.client

from requests.exceptions import RequestException, ConnectionError, Timeout
from requests.auth import HTTPBasicAuth

from source.app_logging import logger
from source.config import BASE_URL, USERNAME, PASSWORD, HEADERS, POLL_INTERVAL


def in_done_stack(card: dict):
    board_id = card['board_id']
    card_id = card['card_id']
    stack_id = card['stack_id']
    all_stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS,
                                   auth=HTTPBasicAuth(USERNAME, PASSWORD))
    all_stacks_resp.raise_for_status()
    data = all_stacks_resp.json()
    if not data:
        return None

    now_stack = next((s['order'] for s in data if s['id'] == stack_id), None)
    if now_stack == 0 or now_stack is None:
        return None

    done_stack = max(data, key=lambda s: (s['order'], s['id'] if s['order'] == 999 else 0))
    if done_stack['order'] == now_stack:
        return None

    new_stack_id = done_stack['id']
    position = 0
    reorder_url = f"{BASE_URL}/boards/{board_id}/stacks/{new_stack_id}/cards/{card_id}/reorder"
    payload = {"stackId": new_stack_id, "order": position}
    move_resp = requests.put(reorder_url, headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD), json=payload)
    if move_resp.status_code not in (200, 204):
        return None
    return [done_stack['title'], new_stack_id]

def _to_hashtag(text: str) -> str | None:
    """
    Преобразует строку в хештег:
    - Добавляет '#' в начале
    - Убирает все запрещённые символы (оставляет буквы, цифры, подчёркивания)
    - Объединяет слова без пробелов
    """

    clean_text = re.sub(r'[^a-zA-Z0-9а-яА-Я_]', '', text)

    if not clean_text:
        return None

    return f'#{clean_text}'

def _extract_counts(card: dict) -> Tuple[int, int]:
    """
    Извлекает количество комментариев и вложений из объекта карточки.
    """
    comments = card.get("commentsCount")
    if comments is None:
        comments = card.get("commentCount", 0)
    atts = card.get("attachmentCount")
    if atts is None:
        atts = card.get("attachmentsCount", 0)
    return int(comments or 0), int(atts or 0)


def _parse_due_utc_naive(value: Any, card_id: Optional[int] = None) -> Optional[datetime]:
    """
    Преобразует дату дедлайна из API в datetime в UTC.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None

        if re.fullmatch(r"\d+(\.\d+)?", s):
            try:
                return _parse_due_utc_naive(float(s), card_id=card_id)
            except Exception:
                logger.debug(f"CLOUD: card {card_id} duedate numeric-str='{value}' -> parse failed")
                return None

        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        m = re.search(r"([+-]\d{2})(\d{2})$", s)
        if m:
            s = s[:m.start()] + f"{m.group(1)}:{m.group(2)}"

        try:
            dt = datetime.fromisoformat(s)
        except Exception as e:
            logger.debug(f"CLOUD: card {card_id} duedate_raw='{value}' -> fromisoformat failed: {e}")
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    if isinstance(value, (int, float)):
        ts = float(value)
        if ts <= 0:
            return None

        if ts > 1_000_000_000_000:
            ts = ts / 1000.0

        dt_epoch = datetime.fromtimestamp(ts, tz=timezone.utc)

        if dt_epoch.year <= 1971 and ts < 60_000_000:
            year = datetime.now(timezone.utc).year
            dt_year = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ts)
            logger.debug(f"CLOUD: card {card_id} duedate_raw={value} -> seconds-from-year-start ({year}) "
                         f"-> {dt_year.isoformat()}")
            return dt_year.replace(tzinfo=None)

        return dt_epoch.replace(tzinfo=None)

    return None


def _parse_done_utc_naive(value: Any, card_id: Optional[int] = None) -> Optional[datetime]:
    """
    Парсит поле "done" карточки и возвращает время завершения
    в формате UTC naive (без tzinfo).
    """
    if value is None or value == "" or value is False or value == 0 or value == "0":
        return None

    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("false", "0", "no", "off", "none", "null"):
            return None
        if s in ("true", "1", "yes", "on"):
            return datetime.utcnow().replace(microsecond=0)

    if value is True or value == 1:
        return datetime.utcnow().replace(microsecond=0)

    return _parse_due_utc_naive(value, card_id=card_id)


def get_board_title(board_id):
    """
    Возвращает название доски по ID.
    """
    boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    boards_resp.raise_for_status()
    boards = boards_resp.json()
    for board in boards:
        if board.get('id') == board_id:
            return board.get('title')
    return None


def fetch_user_tasks(login):
    """
    Получает задачи конкретного пользователя.
    Используется для команды /mycards.
    """
    logger.debug("CLOUD: получаю задачи пользователя")
    result = []
    boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    boards_resp.raise_for_status()
    boards = boards_resp.json()

    for board in boards:
        if board.get('archived', False):
            continue

        board_id = board['id']
        board_title = board['title']

        stacks_resp = requests.get(
            f"{BASE_URL}/boards/{board_id}/stacks?details=true",
            headers=HEADERS,
            auth=HTTPBasicAuth(USERNAME, PASSWORD)
        )
        stacks_resp.raise_for_status()
        stacks = sorted(stacks_resp.json(), key=lambda s: s['order'])

        for idx, stack in enumerate(stacks):
            stack_id = stack['id']
            stack_title = stack['title']

            cards = stack.get('cards') or []
            if not cards:
                sd = requests.get(
                    f"{BASE_URL}/boards/{board_id}/stacks/{stack_id}?details=true",
                    headers=HEADERS,
                    auth=HTTPBasicAuth(USERNAME, PASSWORD)
                )
                sd.raise_for_status()
                cards = sd.json().get('cards', [])

            for card in cards:
                assigned = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                if login not in assigned:
                    continue

                prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None

                duedate_raw = card.get('duedate') or card.get('dueDate')
                duedate_dt = _parse_due_utc_naive(duedate_raw, card_id=card.get('id'))

                done_raw = card.get('done')
                done_dt = _parse_done_utc_naive(done_raw, card_id=card.get('id'))

                comments_count, attachments_count = _extract_counts(card)
                etag = card.get('ETag') or card.get('Etag') or card.get('etag')

                result.append({
                    'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                    'board_id': board_id, 'board_title': board_title,
                    'stack_id': stack_id, 'stack_title': stack_title,
                    'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                    'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                    'duedate': duedate_dt, 'done': done_dt, 'assigned_logins': assigned,
                    'comments_count': comments_count, 'attachments_count': attachments_count,
                    'etag': etag
                })

    return result


def fetch_all_tasks():
    """
    Получает все задачи со всех досок из Nextcloud.
    Используется в scheduler.
    """
    while True:
        logger.debug("CLOUD: получаю все карточки")
        result = []
        try:
            boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
            boards_resp.raise_for_status()
            boards = boards_resp.json()
        except (RequestException, ConnectionError, Timeout,
                http.client.RemoteDisconnected, ConnectionResetError, socket.gaierror) as e:
            logger.warning(f"CLOUD: соединение сброшено/недоступно: {e}. Повтор через {POLL_INTERVAL} секунд.")
            time.sleep(POLL_INTERVAL)
            continue

        for board in boards:
            if board.get('archived', False):
                continue

            board_id = board['id']
            board_title = board['title']

            stacks_resp = requests.get(
                f"{BASE_URL}/boards/{board_id}/stacks?details=true",
                headers=HEADERS,
                auth=HTTPBasicAuth(USERNAME, PASSWORD)
            )
            stacks_resp.raise_for_status()
            stacks = sorted(stacks_resp.json(), key=lambda s: s['order'])

            for idx, stack in enumerate(stacks):
                stack_id = stack['id']
                stack_title = stack['title']

                cards = stack.get('cards') or []
                if not cards:
                    sd = requests.get(
                        f"{BASE_URL}/boards/{board_id}/stacks/{stack_id}?details=true",
                        headers=HEADERS,
                        auth=HTTPBasicAuth(USERNAME, PASSWORD)
                    )
                    sd.raise_for_status()
                    cards = sd.json().get('cards', [])

                for card in cards:
                    duedate_raw = card.get('duedate') or card.get('dueDate')
                    duedate_dt = _parse_due_utc_naive(duedate_raw, card_id=card.get('id'))

                    assigned_logins = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                    labels = [_to_hashtag(lab['title']) for lab in (card.get('labels') or []) if _to_hashtag(lab['title'])]

                    prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                    prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                    next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                    next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None

                    comments_count, attachments_count = _extract_counts(card)
                    done_raw = card.get('done')
                    done = _parse_done_utc_naive(done_raw, card_id=card.get('id'))
                    etag = card.get('ETag') or card.get('Etag') or card.get('etag')
                    lastModified = (datetime.now() - datetime.fromtimestamp(card['lastModified'])).total_seconds()

                    result.append({
                        'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                        'board_id': board_id, 'board_title': board_title,
                        'stack_id': stack_id, 'stack_title': stack_title,
                        'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                        'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                        'duedate': duedate_dt, 'done': done,
                        'assigned_logins': assigned_logins,
                        'comments_count': comments_count, 'attachments_count': attachments_count,
                        'labels': labels,
                        'etag': etag, 'lastModified': int(lastModified)
                    })

        return result
