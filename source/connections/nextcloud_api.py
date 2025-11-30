import time
from datetime import datetime, timezone
from typing import Tuple

import requests
import socket, http.client
from requests.exceptions import RequestException, ConnectionError, Timeout
from requests.auth import HTTPBasicAuth
from source.app_logging import logger
from source.config import BASE_URL, USERNAME, PASSWORD, HEADERS, POLL_INTERVAL

def _extract_counts(card: dict) -> Tuple[int, int]:
    comments = card.get("commentsCount")
    if comments is None:
        comments = card.get("commentCount", 0)
    atts = card.get("attachmentCount")
    if atts is None:
        atts = card.get("attachmentsCount", 0)
    # if isinstance(card.get("attachments"), list):
    #     atts = max(atts, len(card["attachments"]))
    return int(comments or 0), int(atts or 0)


def get_board_title(board_id):
    logger.debug("CLOUD: получаю список досок для поиска title")
    resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    resp.raise_for_status()
    for board in resp.json():
        if board.get('id') == board_id:
            return board.get('title')
    return None

def fetch_user_tasks(login):
    logger.debug("CLOUD: получаю задачи пользователя")
    result = []
    boards_resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    boards_resp.raise_for_status()
    boards = boards_resp.json()
    for board in boards:
        if board.get('archived', True):
            continue
        board_id = board['id']; board_title = board['title']
        stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
        stacks_resp.raise_for_status()
        stacks = sorted(stacks_resp.json(), key=lambda s: s['order'])
        for idx, stack in enumerate(stacks):
            stack_id = stack['id']; stack_title = stack['title']
            cards = stack.get('cards') or []
            if not cards:
                sd = requests.get(f"{BASE_URL}/boards/{board_id}/stacks/{stack_id}?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
                sd.raise_for_status(); cards = sd.json().get('cards', [])
            for card in cards:
                assigned = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                if login in assigned:
                    prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                    prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                    next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                    next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None
                    duedate_iso = card.get('duedate'); duedate_dt = None
                    if duedate_iso:
                        duedate_dt = datetime.fromisoformat(duedate_iso).astimezone(timezone.utc).replace(tzinfo=None)
                    comments_count, attachments_count = _extract_counts(card)
                    result.append({
                        'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                        'board_id': board_id, 'board_title': board_title,
                        'stack_id': stack_id, 'stack_title': stack_title,
                        'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                        'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                        'duedate': duedate_dt, 'assigned_logins': assigned,
                        'comments_count': comments_count, 'attachments_count': attachments_count
                    })
    return result

def fetch_all_tasks():
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
            if board.get('archived', True):
                continue
            board_id = board['id']; board_title = board['title']
            stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
            stacks_resp.raise_for_status()
            stacks = sorted(stacks_resp.json(), key=lambda s: s['order'])
            for idx, stack in enumerate(stacks):
                stack_id = stack['id']; stack_title = stack['title']
                cards = stack.get('cards') or []
                if not cards:
                    sd = requests.get(f"{BASE_URL}/boards/{board_id}/stacks/{stack_id}?details=true", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
                    sd.raise_for_status(); cards = sd.json().get('cards', [])
                for card in cards:
                    duedate_iso = card.get('duedate'); duedate_dt = None
                    if duedate_iso:
                        duedate_dt = datetime.fromisoformat(duedate_iso).astimezone(timezone.utc).replace(tzinfo=None)
                    assigned_logins = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                    prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                    prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                    next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                    next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None

                    comments_count = None
                    attachments_count = None
                    if 'commentsCount' in card or 'attachmentCount' in card:
                        comments_count = card.get('commentsCount') or 0
                        attachments_count = card.get('attachmentCount') or 0
                    else:
                        if 'commentsCount' in card: comments_count = int(card['commentsCount'])
                        if 'attachmentCount' in card: attachments_count = int(card['attachmentCount'])

                    if comments_count is None: comments_count = 0
                    if attachments_count is None: attachments_count = 0

                    done = card.get('done')

                    result.append({
                        'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                        'board_id': board_id, 'board_title': board_title,
                        'stack_id': stack_id, 'stack_title': stack_title,
                        'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                        'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                        'duedate': duedate_dt, 'done': done,
                        'assigned_logins': assigned_logins,
                        'comments_count': comments_count, 'attachments_count': attachments_count
                    })
        return result
