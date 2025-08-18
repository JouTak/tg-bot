from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from source.app_logging import logger
from source.connections.nextcloud_api import fetch_all_tasks
from source.db.repos.users import get_user_map
from source.db.repos.deadlines import get_sent_map_for_period, mark_sent
from source.connections.sender import send_message_limited
from source.links import card_url

from source.config import DEADLINES_INTERVAL, TIMEZONE, QUIET_HOURS, DEADLINE_REPEAT_DAYS

DEADLINES_INTERVAL = int(DEADLINES_INTERVAL)

try:
    TEAM_TZ = ZoneInfo(TIMEZONE)
except Exception:
    TEAM_TZ = timezone(timedelta(hours=3))

def _parse_quiet(s: str) -> tuple[int, int]:
    try:
        a, b = s.split('-', 1)
        return int(a), int(b)
    except Exception:
        return (0, 1)

QUIET_START, QUIET_END = _parse_quiet(QUIET_HOURS)

def _at_team_10(utc_dt: datetime) -> datetime:
    local = utc_dt.astimezone(TEAM_TZ)
    local10 = local.replace(hour=10, minute=0, second=0, microsecond=0)
    return local10.astimezone(timezone.utc)

def _schedule_points(due_utc: datetime) -> dict[str, datetime]:
    sched = {
        "pre_7d": _at_team_10(due_utc - timedelta(days=7)),
        "pre_24h": _at_team_10(due_utc - timedelta(days=1)),
        "pre_2h": due_utc - timedelta(hours=2),
        "due": due_utc,
        "post_2h": due_utc + timedelta(hours=2),
        "post_24h": _at_team_10(due_utc + timedelta(days=1)),
    }

    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    if now > due_utc + timedelta(days=1):
        days_over = (now - due_utc).days
        if days_over >= 1:
            repeat_day = days_over - (days_over % DEADLINE_REPEAT_DAYS)
            sched["post_repeat"] = _at_team_10(due_utc + timedelta(days=repeat_day))
    return sched

def _in_quiet_hours(now_local: datetime) -> bool:
    h = now_local.hour
    return (h >= QUIET_START) or (h < QUIET_END) if QUIET_START > QUIET_END else (QUIET_START <= h < QUIET_END)

def _fmt_due_local(due_utc: datetime) -> str:
    return due_utc.astimezone(TEAM_TZ).strftime("%Y-%m-%d %H:%M")

def _fmt_delta(now: datetime, due: datetime) -> str:
    delta = due - now
    neg = delta.total_seconds() < 0
    sec = int(abs(delta).total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, _ = divmod(sec, 60)
    s = f"{d}д {h}ч" if d else (f"{h}ч {m}м" if h else f"{m}м")
    return f"-{s}" if neg else s

def _line_for_stage(stage: str, item: dict, now_utc: datetime) -> str:
    cid = item["card_id"]; title = item["title"]; due = item["duedate"]
    link = f'<a href="{card_url(item["board_id"], cid)}">{cid}</a>'
    rel = _fmt_delta(now_utc, due)
    due_s = _fmt_due_local(due)
    prefix = {
        "pre_7d":   "📅 Через неделю",
        "pre_24h":  "🌝 Завтра",
        "pre_2h":   "⏳ Через ~2 часа",
        "due":      "🔔 Срок наступил",
        "post_2h":  "⚠️ Просрочено на ~2 часа",
        "post_24h": "🌚 Просрочено более чем на сутки",
        "post_repeat": f"🔁 Просрочено уже {(now_utc - due).days} дн.",
    }.get(stage, "⏰ Напоминание")
    return f"— {prefix}: «{title}» — ID: {link} — {due_s} (Δ {rel})"

def poll_deadlines():
    logger.info(f"DEADLINES: старт фонового опроса, частота {DEADLINES_INTERVAL} сек!")
    while True:
        try:
            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            now_local = now_utc.astimezone(TEAM_TZ)

            if _in_quiet_hours(now_local):
                time.sleep(DEADLINES_INTERVAL)
                continue

            login_map = get_user_map()
            cards = fetch_all_tasks()

            for c in cards:
                if c.get("duedate") and c["duedate"].tzinfo is None:
                    c["duedate"] = c["duedate"].replace(tzinfo=timezone.utc)

            sent_map = get_sent_map_for_period()
            per_user: dict[str, list[tuple[str, str, int]]] = {}

            STAGE_ORDER = ["pre_7d", "pre_24h", "pre_2h", "due", "post_2h", "post_24h", "post_repeat"]
            RANK = {s: i for i, s in enumerate(STAGE_ORDER)}

            for item in cards:
                due = item.get("duedate")
                if not due:
                    continue
                if item.get("done") is not None:
                    continue
                if item.get("archived"):
                    continue
                assigned = set(item.get("assigned_logins") or [])
                if not assigned:
                    continue

                sched = _schedule_points(due)
                for login in assigned:
                    already = sent_map.get((item["card_id"], login), set())
                    candidates = [s for s, ts in sched.items() if s not in already and now_utc >= ts]
                    if not candidates:
                        continue
                    chosen = max(candidates, key=lambda s: RANK[s])
                    per_user.setdefault(login, []).append(
                        (chosen, _line_for_stage(chosen, item, now_utc), item["card_id"], candidates)
                    )

            priority = {"due": 0, "post_2h": 1, "post_24h": 2, "post_repeat": 3, "pre_2h": 4, "pre_24h": 5, "pre_7d": 6}
            for login, entries in per_user.items():
                tg_id = login_map.get(login)
                if not tg_id:
                    continue
                entries.sort(key=lambda x: (priority.get(x[0], 9), x[2]))
                body = "\n".join(e[1] for e in entries)
                ok = send_message_limited(tg_id, f"⏰ Напоминания о дедлайнах:\n{body}")
                if ok:
                    for stage, _, card_id, candidates in entries:
                        try:
                            for s in candidates:
                                if RANK[s] <= RANK[stage]:
                                    mark_sent(card_id, login, s)
                        except Exception as e:
                            logger.warning(
                                f"DEADLINES: не удалось отметить отправку ({card_id}, {login}, {stage}): {e}"
                            )
                else:
                    logger.warning(f"DEADLINES: уведомления {login} ({tg_id}) не доставлены, пропускаю mark_sent")
        except Exception as e:
            logger.exception(f"DEADLINES: сбой цикла: {e}")
        time.sleep(DEADLINES_INTERVAL)
