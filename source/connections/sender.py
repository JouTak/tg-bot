import time
import html
import re
from collections import deque, defaultdict
import requests
from telebot.apihelper import ApiException
from source.connections.bot_factory import bot
from source.app_logging import logger

def _fmt_duration(seconds: float) -> str:
    if seconds < 1: return f"{int(round(seconds * 1000))} ms"
    if seconds < 60: return f"{seconds:.2f} s"
    m, s = divmod(int(round(seconds)), 60); return f"{m}m {s}s"

class TokenBucket:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
    def wait(self):
        now = time.time()
        while self.calls and self.calls[0] <= now - self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                logger.debug(f"Пауза {_fmt_duration(sleep_time)} (лимит {self.max_calls}/{int(self.period)}s)")
                time.sleep(sleep_time)
        self.calls.append(time.time())

_global = TokenBucket(max_calls=30, period=1.0)   # ~30/s суммарно
_per_chat = defaultdict(lambda: TokenBucket(max_calls=1, period=1.0))  # ~1/s в чат

_bold_pat = re.compile(r'\*(.+?)\*')       # *bold* -> <b>…</b>
_code_pat = re.compile(r'`(.+?)`')         # `code` -> <code>…</code>
_a_tag_pat = re.compile(r'<a\s+href="https?://[^"]+">.*?</a>', re.IGNORECASE | re.DOTALL)
_quote_pat = re.compile(r'\\\\\\(.+?)///', re.IGNORECASE | re.DOTALL)
_pre_pat = re.compile(r'```(.+?)```', re.IGNORECASE | re.DOTALL)
def _auto_html(text: str | None) -> str:
    """
       *жирный*  -> <b>жирный</b>
       `код`     -> <code>код</code>
       \\\цитата/// -> <blockquote>цитата</blockquote>
       большой код -> <pre>большой код</pre>
    """
    if not text:
        return ""
    raw = str(text)
    anchors = []
    def _stash(m):
        anchors.append(m.group(0))
        return f"__ANCHOR_{len(anchors) - 1}__"
    stashed = _a_tag_pat.sub(_stash, raw)

    s = html.escape(stashed, quote=False)
    s = _quote_pat.sub(lambda m: f"<blockquote>{m.group(1)}</blockquote>", s)
    s = _pre_pat.sub(lambda m: f"<pre>{m.group(1)}</pre>", s)
    s = _bold_pat.sub(lambda m: f"<b>{m.group(1)}</b>", s)
    s = _code_pat.sub(lambda m: f"<code>{m.group(1)}</code>", s)

    for i, tag in enumerate(anchors):
        s = s.replace(f"__ANCHOR_{i}__", tag)
    return s

def send_message_limited(chat_id: int, text: str, **kwargs):
    _global.wait()
    _per_chat[chat_id].wait()

    safe_text = _auto_html(text)
    kwargs.pop("parse_mode", None)
    kwargs["parse_mode"] = "HTML"
    try:
        return bot.send_message(chat_id, safe_text, **kwargs)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        logger.warning(f"Не смог отправить сообщение в chat_id={chat_id}: сеть недоступна ({'таймаут' if isinstance(e, requests.exceptions.Timeout) else 'нет соединения'}).")
        return None
    except ApiException as e:
        logger.warning(f"Ошибка Telegram API при отправке в chat_id={chat_id}: {e}")
        return None
#
# def send_bulk_text(chat_id: int, lines: list[str], header: str | None = None,
#                    footer: str | None = None, **kwargs):
#     parts = []
#     if header: parts.append(header)
#     parts.extend(lines)
#     if footer: parts.append(footer)
#     return send_message_limited(chat_id, "\n".join(parts), **kwargs)
