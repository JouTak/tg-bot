from urllib.parse import urlsplit, urlunsplit
from source.config import BASE_URL


def _deployment_root() -> str:
    """
    Из BASE_URL (обычно .../index.php/apps/deck/api/v1.0) получаем корень развертывания:
      https://host              -> если в корне
      https://host/subdir       -> если Nextcloud живет в подкаталоге
    """
    parts = urlsplit(BASE_URL)
    path = parts.path or ""
    cut_at = len(path)

    for marker in ("/index.php", "/apps/deck", "/remote.php"):
        pos = path.find(marker)
        if pos != -1:
            cut_at = min(cut_at, pos)

    base_path = path[:cut_at].rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, base_path, "", ""))


def card_url(board_id: int | str, card_id: int | str) -> str:
    """
    Каноничная ссылка на карточку Deck:
      https://<host>[/subdir]/apps/deck/board/<boardId>/card/<cardId>
    """
    root = _deployment_root().rstrip("/")
    return f"{root}/apps/deck/board/{board_id}/card/{card_id}"
