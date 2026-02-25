from __future__ import annotations

import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from source.app_logging import logger
from source.connections.nextcloud_api import fetch_all_tasks
from source.db.repos.users import get_user_map
from source.db.repos.tasks import get_saved_tasks, get_saved_tasks_for_deadlines
from source.db.repos.deadlines import get_last_sent_map, mark_sent, reset_sent_for_card
from source.connections.sender import send_message_limited
from source.links import card_url

from source.config import DEADLINES_INTERVAL, TIMEZONE, QUIET_HOURS, DEADLINE_REPEAT_DAYS, EXCLUDED_CARD_IDS


DEADLINES_INTERVAL = int(DEADLINES_INTERVAL)

try:
    TEAM_TZ = ZoneInfo(TIMEZONE)
except Exception:
    TEAM_TZ = timezone(timedelta(hours=3))


def _should_notify(card_id: int) -> bool:
    """Возвращает True, если по карточке можно отправлять уведомления."""
    return card_id not in EXCLUDED_CARD_IDS

def _parse_quiet(s: str) -> tuple[int, int]:
    """
    Парсит строку формата "0-8" в часы тихого режима.
    """
    try:
        a, b = s.split("-", 1)
        return int(a), int(b)
    except Exception:
        return (0, 1)


QUIET_START, QUIET_END = _parse_quiet(QUIET_HOURS)


def _in_quiet_hours(now_local: datetime) -> bool:
    """
    Проверяет, попадает ли текущее время в тихие часы.
    """
    h = now_local.hour
    if QUIET_START > QUIET_END:
        return (h >= QUIET_START) or (h < QUIET_END)
    return QUIET_START <= h < QUIET_END


def _at_team_10(utc_dt: datetime) -> datetime:
    """
    Переводит дату в 10:00 по часовому поясу команды.
    Используется для фиксированных напоминаний.
    """
    local = utc_dt.astimezone(TEAM_TZ)
    local10 = local.replace(hour=10, minute=0, second=0, microsecond=0)
    return local10.astimezone(timezone.utc)


def _fixed_schedule(due_utc: datetime) -> dict[str, datetime]:
    """
    Формирует расписание напоминаний:
    - за 7 дней
    - за 24 часа
    - за 2 часа
    - в момент дедлайна
    - после дедлайна
    """
    return {
        "pre_7d": _at_team_10(due_utc - timedelta(days=7)),
        "pre_24h": _at_team_10(due_utc - timedelta(days=1)),
        "pre_2h": due_utc - timedelta(hours=2),
        "due": due_utc,
        "post_2h": due_utc + timedelta(hours=2),
        "post_24h": _at_team_10(due_utc + timedelta(days=1)),
    }


def _fmt_due_local(due_utc: datetime) -> str:
    """
    Форматирует дедлайн в локальное время команды.
    """
    return due_utc.astimezone(TEAM_TZ).strftime("%Y-%m-%d %H:%M")


def _fmt_delta(now: datetime, due: datetime) -> str:
    """
    Возвращает человекочитаемую разницу между текущим временем и дедлайном.
    """
    delta = due - now
    neg = delta.total_seconds() < 0
    sec = int(abs(delta).total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, _ = divmod(sec, 60)
    s = f"{d}д {h}ч" if d else (f"{h}ч {m}м" if h else f"{m}м")
    return f"-{s}" if neg else s


def _line_for_stage(stage: str, item: dict, now_utc: datetime) -> str:
    """
    Формирует строку уведомления для конкретного этапа напоминания.
    """
    cid = item["card_id"]
    title = item["title"]
    due = item["duedate"]
    link = f'<a href="{card_url(item["board_id"], cid)}">{cid}</a>'
    rel = _fmt_delta(now_utc, due)
    due_s = _fmt_due_local(due)

    prefix = {
        "pre_7d": "📅 Через неделю",
        "pre_24h": "🌝 Завтра",
        "pre_2h": "⏳ Через ~2 часа",
        "due": "🔔 Срок наступил",
        "post_2h": "⚠️ Просрочено на ~2 часа",
        "post_24h": "🌚 Просрочено на день",
        "post_repeat": f"🔁 Просрочено уже {(now_utc - due).days} дн.",
    }.get(stage, "⏰ Напоминание")

    return f"— {prefix}: «{title}» — ID: {link} — {due_s} (Δ {rel})"


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    """
    Приводит datetime к UTC без tzinfo (naive UTC).
    """
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _sent_at_to_utc(sent_at: datetime) -> datetime:
    """
    Приводит datetime к UTC с сохранением tzinfo.
    """
    if sent_at.tzinfo is None:
        return sent_at.replace(tzinfo=timezone.utc)
    return sent_at.astimezone(timezone.utc)


def poll_deadlines():
    """
    Фоновый цикл проверки дедлайнов:
    - проверяет задачи с дедлайнами
    - определяет, какие уведомления нужно отправить
    - отправляет их пользователям
    - записывает факт отправки в БД
    """
    logger.info(f"DEADLINES: Запускается фоновый опрос, частота {DEADLINES_INTERVAL} секунд!")

    FIXED = ["pre_7d", "pre_24h", "pre_2h", "due", "post_2h", "post_24h"]
    FIXED_RANK = {s: i for i, s in enumerate(FIXED)}
    DUE_RANK = FIXED_RANK["due"]
    POST24_RANK = FIXED_RANK["post_24h"]

    while True:
        try:
            logger.info("DEADLINES: Начинается плановая проверка дедлайнов")

            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            now_local = now_utc.astimezone(TEAM_TZ)

            if _in_quiet_hours(now_local):
                logger.info("DEADLINES: тихие часы, пропуск.")
                time.sleep(DEADLINES_INTERVAL)
                continue

            repeat_days = int(DEADLINE_REPEAT_DAYS)
            repeat_delta = timedelta(days=repeat_days) if repeat_days > 0 else None

            login_map = get_user_map()

            t0 = time.time()
            cards = get_saved_tasks_for_deadlines()
            fetch_sec = time.time() - t0

            for c in cards:
                if c.get("duedate") and c["duedate"].tzinfo is None:
                    c["duedate"] = c["duedate"].replace(tzinfo=timezone.utc)

            last_map = get_last_sent_map()
            per_user: dict[str, list[tuple[str, str, int]]] = {}

            with_due = 0
            active_due = 0

            for item in cards:
                due = item.get("duedate")
                if not due:
                    continue
                with_due += 1

                if (item.get("done") is not None) or ((item.get("done") is None) and (item.get("prev_stack_id") is None) and (item.get("next_stack_id") is None)):
                    continue

                assigned = set(item.get("assigned_logins") or [])
                if not assigned:
                    continue

                active_due += 1

                fixed_sched = _fixed_schedule(due)
                post24_time = fixed_sched["post_24h"]
                repeat_zone = (repeat_delta is not None) and (now_utc >= (post24_time + repeat_delta))

                for login in assigned:
                    last = last_map.get((item["card_id"], login))
                    last_stage = last[0] if last else None
                    last_sent_at = last[1] if last else None
                    last_sent_utc = _sent_at_to_utc(last_sent_at) if last_sent_at else None

                    last_fixed_rank = -1
                    if last_stage in FIXED_RANK:
                        last_fixed_rank = FIXED_RANK[last_stage]
                    elif last_stage == "post_repeat":
                        last_fixed_rank = POST24_RANK

                    if now_utc < due and last_fixed_rank >= DUE_RANK:
                        try:
                            reset_sent_for_card(item["card_id"])
                        except Exception:
                            pass
                        last_stage = None
                        last_fixed_rank = -1
                        last_sent_utc = None
                        last_sent_at = None

                    chosen_stage = None

                    if repeat_zone:
                        if last_stage != "post_repeat":
                            chosen_stage = "post_repeat"
                        else:
                            if repeat_delta is not None and last_sent_utc is not None and (now_utc - last_sent_utc >= repeat_delta):
                                chosen_stage = "post_repeat"
                    else:
                        candidates = [
                            s for s, ts in fixed_sched.items()
                            if FIXED_RANK[s] > last_fixed_rank and now_utc >= ts
                        ]
                        if candidates:
                            chosen_stage = max(candidates, key=lambda s: FIXED_RANK[s])

                    if not chosen_stage:
                        continue

                    per_user.setdefault(login, []).append(
                        (chosen_stage, _line_for_stage(chosen_stage, item, now_utc), item["card_id"])
                    )

            total_items = sum(len(v) for v in per_user.values())
            logger.info(
                f"DEADLINES: fetch={fetch_sec:.2f}s cards={len(cards)} with_due={with_due} active_due={active_due} "
                f"users_to_notify={len(per_user)} reminders={total_items}"
            )

            if total_items == 0:
                time.sleep(DEADLINES_INTERVAL)
                continue

            priority = {
                "due": 0,
                "post_2h": 1,
                "post_24h": 2,
                "post_repeat": 3,
                "pre_2h": 4,
                "pre_24h": 5,
                "pre_7d": 6,
            }
            if _should_notify(item["card_id"]):
                for login, entries in per_user.items():
                    tg_id = login_map.get(login)
                    if not tg_id:
                        continue

                    entries.sort(key=lambda x: (priority.get(x[0], 9), x[2]))
                    body = "\n".join(e[1] for e in entries)

                    ok = send_message_limited(tg_id, f"⏰ Напоминания о дедлайнах:\n{body}")
                    if ok:
                        for stage, _, card_id in entries:
                            try:
                                mark_sent(card_id, login, stage)
                            except Exception as e:
                                logger.error(f"DEADLINES: не удалось отметить отправку ({card_id}, {login}, {stage}): {e}")
                                logger.debug(traceback.format_exc())
                    else:
                        logger.warning(f"DEADLINES: уведомления {login} ({tg_id}) не доставлены, пропускаю mark_sent")

        except Exception:
            logger.exception("DEADLINES: сбой цикла")
            logger.debug(traceback.format_exc())

        time.sleep(DEADLINES_INTERVAL)
