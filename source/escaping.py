"""Санитизация пользовательского контента для rich-markdown (sendRichMessage).

Правила рендерера (probe / probe2 / probe_quote):
- верхний уровень: парсятся HTML-подмножество И markdown (_ * ` ``` - [ ]),
  backslash-экранирование работает => sanitize() = html.escape + backslash;
- внутри <blockquote>: HTML парсится, markdown НЕ парсится, backslash НЕ
  работает => escape_html() = только html.escape;
- entity (&#95;, &lt; ...) декодируются и там, и там;
- ```-fence внутри <blockquote> не работает; <pre> внутри <blockquote> работает.
"""
import html
import re

_FENCE_RE = re.compile(r"```[\w-]*\n(?P<body>.*?)```", re.S)
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def sanitize(text) -> str:
    """Верхний уровень: html.escape + backslash для markdown-спецсимволов."""
    s = html.escape(str(text if text is not None else ""), quote=False)
    for ch in ("_", "*", "`"):
        s = s.replace(ch, "\\" + ch)
    return s


def escape_html(text) -> str:
    """Внутри <blockquote>: только html.escape (markdown там неактивен)."""
    return html.escape(str(text if text is not None else ""), quote=False)


def code_text(text) -> str:
    """Контент для <code>/<pre>: только html.escape."""
    return html.escape(str(text if text is not None else ""), quote=False)


def _blocks(text, esc):
    parts = []

    def repl(m):
        parts.append("<pre>" + code_text(m.group("body")) + "</pre>")
        return f"\x00{len(parts) - 1}\x00"

    s = _FENCE_RE.sub(repl, str(text if text is not None else ""))
    s = esc(s)
    return _PLACEHOLDER_RE.sub(lambda m: parts[int(m.group(1))], s)


def user_block(text) -> str:
    """Пользовательский блок верхнего уровня."""
    return _blocks(text, sanitize)


def user_block_q(text) -> str:
    """Пользовательский блок внутри <blockquote>."""
    return _blocks(text, escape_html)
