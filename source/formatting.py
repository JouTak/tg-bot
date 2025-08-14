# import re
#
# _MD2_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}\.!])')
#
# def mdv2_escape(text: str | None) -> str:
#     if not text:
#         return ""
#     return _MD2_RE.sub(r'\\\1', str(text))
#
# def mdv2_code(text: str | None) -> str:
#     """
#     Безопасный inline code для MarkdownV2:
#     экранируем обратный апостроф и обратный слеш, затем оборачиваем в `...`
#     """
#     if text is None:
#         text = ""
#     s = str(text).replace('\\', '\\\\').replace('`', r'\`')
#     return f'`{s}`'
