from datetime import datetime, timezone
import requests
from requests.auth import HTTPBasicAuth
from source.app_logging import logger
from source.config import BASE_URL, USERNAME, PASSWORD, HEADERS

def get_board_title(board_id):
    logger.debug("Nextcloud: получаю список досок для поиска title")
    resp = requests.get(f"{BASE_URL}/boards", headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    resp.raise_for_status()
    for board in resp.json():
        if board.get('id') == board_id:
            return board.get('title')
    return None

def fetch_user_tasks(login):
    logger.debug("Nextcloud: получаю задачи пользователя")
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
                    result.append({
                        'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                        'board_id': board_id, 'board_title': board_title,
                        'stack_id': stack_id, 'stack_title': stack_title,
                        'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                        'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                        'duedate': duedate_dt
                    })
    return result

def fetch_all_tasks():
    logger.debug("Nextcloud: получаю все карточки")
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
                duedate_iso = card.get('duedate'); duedate_dt = None
                if duedate_iso:
                    duedate_dt = datetime.fromisoformat(duedate_iso).astimezone(timezone.utc).replace(tzinfo=None)
                assigned_logins = [u['participant']['uid'] for u in (card.get('assignedUsers') or [])]
                prev_stack_id = stacks[idx - 1]['id'] if idx > 0 else None
                prev_stack_title = stacks[idx - 1]['title'] if idx > 0 else None
                next_stack_id = stacks[idx + 1]['id'] if idx < len(stacks) - 1 else None
                next_stack_title = stacks[idx + 1]['title'] if idx < len(stacks) - 1 else None
                result.append({
                    'card_id': card['id'], 'title': card['title'], 'description': card.get('description', ''),
                    'board_id': board_id, 'board_title': board_title,
                    'stack_id': stack_id, 'stack_title': stack_title,
                    'prev_stack_id': prev_stack_id, 'prev_stack_title': prev_stack_title,
                    'next_stack_id': next_stack_id, 'next_stack_title': next_stack_title,
                    'duedate': duedate_dt, 'assigned_logins': assigned_logins
                })
    return result
