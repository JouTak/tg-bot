# ITMOcraft Telegram Bot — Архитектура

## Обзор
Telegram-бот для команды ITMOcraft, интегрирующий Nextcloud Deck (канбан-доски) и CalDAV-календарь с уведомлениями. Работает на **pyTelegramBotAPI** + **MySQL** + **SQLAlchemy/Alembic**.

---

## Структура проекта
```
tg-bot/
├── source/
│   ├── __main__.py          # Точка входа (вызывает app.run())
│   ├── app.py                # Инициализация бота, запуск фоновых потоков
│   ├── config.py             # Конфигурация из .env
│   ├── handlers.py           # Команды Telegram (/start, /register, /mycards, /calendar, /commit, /whereami, /setboardtopic)
│   ├── callbacks.py          # Обработчики inline-кнопок (move:, check, cal_*)
│   ├── scheduler.py          # Фоновый поллинг Nextcloud Deck (poll_new_tasks)
│   ├── deadlines.py          # Напоминания о дедлайнах (poll_deadlines)
│   ├── nc_calendar.py        # Интеграция CalDAV-календаря Nextcloud
│   ├── links.py              # Генерация URL карточек Deck
│   ├── logging_service.py    # Отправка логов в форум-топики
│   ├── app_logging.py        # Настройка логгера (logging)
│   ├── requirements.txt      # Python-зависимости
│   │
│   ├── connections/
│   │   ├── bot_factory.py    # Создание экземпляра TeleBot
│   │   ├── sender.py         # Rate-limited отправка сообщений + auto-HTML
│   │   └── nextcloud_api.py  # REST API Nextcloud Deck
│   │
│   ├── db/
│   │   ├── db.py             # MySQL-подключение + SQLAlchemy engine
│   │   └── repos/
│   │       ├── users.py      # CRUD пользователей (tg_id ↔ nc_login/token)
│   │       ├── tasks.py      # CRUD задач (карточки Deck)
│   │       ├── boards.py     # Привязка досок к топикам форума
│   │       ├── deadlines.py  # Отслеживание отправленных напоминаний
│   │       └── caldav_calendar.py  # Кэш отправленных CalDAV-событий
│   │
│   └── migrations/
│       ├── models.py         # SQLAlchemy ORM-модели
│       ├── migration.py      # auto_migrate() — авто-миграции
│       └── init_db.py        # Создание таблиц при старте
│
├── alembic/                  # Alembic-миграции (по необходимости)
├── alembic.ini
├── init.sql                  # Начальная схема БД (для ручного деплоя)
├── Dockerfile                # Docker-образ (python:3.11-slim)
├── entrypoint.sh             # Docker entrypoint
└── .env (не в git)           # Переменные окружения
```

---

## Конфигурация (.env)
| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram-бота |
| `BASE_URL` | URL Deck API: `https://cloud.../index.php/apps/deck/api/v1.0` |
| `OCS_BASE_URL` | URL OCS API: `https://cloud.../ocs/v2.php/apps` |
| `WEB_APP_URL` | Корень Nextcloud для OAuth-авторизации |
| `WEB_CALDAV_URL` | URL CalDAV-сервера |
| `NEXTCLOUD_USER` | Логин сервисного пользователя (нужен админ для sync) |
| `NEXTCLOUD_PASS` | Пароль сервисного пользователя |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASS`, `MYSQL_DB` | Подключение к MySQL |
| `FORUM_CHAT_ID` | ID супергруппы с форумом для логов |
| `BOT_LOG_TOPIC_ID` | ID топика по умолчанию для логов |
| `BOT_START_MESSAGE_TOPIC_ID` | ID топика для уведомлений о перезапуске |
| `POLL_INTERVAL` | Интервал опроса Deck (секунды, по умолчанию 60) |
| `DEADLINES_INTERVAL` | Интервал проверки дедлайнов (секунды, по умолчанию 2) |
| `QUIET_HOURS` | Тихие часы (формат `0-8`) — без напоминаний |
| `DEADLINE_REPEAT_DAYS` | Повтор напоминания о просрочке (дни) |
| `ARCHIVE_AFTER_DAYS` | Автоархивация готовых карточек (дни) |
| `EXCLUDED_CARD_IDS` | ID карточек без уведомлений (через запятую) |
| `APP_DEBUG` | `1` для debug-логов |
| `COOLDOWN_TUESDAY/SUNDAY/DEFAULT` | Окно поиска CalDAV-событий (часы) |
| `UPDATE_INTERVAL` | Синхронизация пользователей NC (дни) |

---

## Telegram-команды
| Команда | Где работает | Описание |
|---------|--------------|----------|
| `/start` | ЛС | Приветствие + ссылка на анкету |
| `/register` | ЛС | OAuth-авторизация через Nextcloud (Login Flow v2) |
| `/mycards` | ЛС | Список активных карточек пользователя с кнопками перемещения |
| `/calendar` | ЛС | События на ближайшую неделю с кнопками RSVP |
| `/commit` | ЛС | Текущий git-коммит бота |
| `/whereami` | Любой | Показывает chat_id и thread_id (для настройки) |
| `/setboardtopic <board_id>` | Супергруппа (топик) | Привязывает топик к доске для логов |

---

## Inline-кнопки (callbacks)
| Префикс | Формат | Действие |
|---------|--------|----------|
| `move:` | `move:{board}:{old_stack}:{card}:{new_stack}` | Перемещает карточку между колонками |
| `check` | `check` | Проверяет OAuth-poll и сохраняет токен |
| `cal_` | `cal_{action}_{event_id}_{current_status}` | RSVP: ACCEPTED/DECLINED/TENTATIVE |

---

## Фоновые потоки
При запуске `app.run()` стартуют 4 daemon-потока:

1. **poll_new_tasks()** (`scheduler.py`)
   - Цикл с интервалом `POLL_INTERVAL`
   - Получает все карточки со всех досок Nextcloud Deck
   - Сравнивает с локальной БД (по etag)
   - Отправляет уведомления о: новых карточках, изменениях (колонка, дедлайн, заголовок, описание), новых комментариях/вложениях
   - Автоматически архивирует карточки, готовые дольше `ARCHIVE_AFTER_DAYS`
   - Карточки из `EXCLUDED_CARD_IDS` обрабатываются в БД, но без уведомлений

2. **poll_deadlines()** (`deadlines.py`)
   - Цикл с интервалом `DEADLINES_INTERVAL`
   - Формирует расписание напоминаний (за 24ч, в момент дедлайна, повтор просрочки)
   - Пропускает тихие часы (`QUIET_HOURS`)
   - Отправляет напоминания назначенным пользователям
   - Сбрасывает напоминания при переносе дедлайна

3. **poll_events()** (`nc_calendar.py`)
   - Цикл с интервалом `POLL_INTERVAL`
   - Ищет CalDAV-события на ближайшие `COOLDOWN_*` часов
   - Уведомляет участников о новых событиях с RSVP-кнопками
   - Удаляет из кэша прошедшие события

4. **sync_nextcloud_users()** (`nc_calendar.py`)
   - Цикл с интервалом `UPDATE_INTERVAL` дней
   - Синхронизирует email пользователей из Nextcloud в БД
   - Требует права администратора у сервисного пользователя

---

## База данных (MySQL)
### Основные таблицы
| Таблица | Назначение |
|---------|------------|
| `users` | tg_id → nc_login, nc_email, nc_token |
| `tasks` | Локальный кэш карточек Deck (card_id, title, description, stack_id, duedate, done, etag...) |
| `task_assignees` | Связь карточка → назначенные логины |
| `task_stats` | Счётчики комментариев и вложений |
| `task_labels` | Метки карточек |
| `task_attachments` | file_id вложений (для отслеживания изменений) |
| `task_comments` | comment_id комментариев |
| `deadline_reminders` | Отслеживание отправленных напоминаний (card_id, login, stage, sent_at) |
| `board_log_topics` | Привязка board_id → message_thread_id |
| `login_token` | Временные токены OAuth-авторизации |
| `caldav_send_data` | Кэш отправленных CalDAV-событий (event_name, url) |

### Миграции
- `init_db()` — создаёт таблицы через SQLAlchemy metadata.create_all()
- `auto_migrate()` — добавляет недостающие колонки (nc_email, nc_token в users и др.)
- Alembic настроен, но миграции применяются программно при старте

---

## Nextcloud API
### Deck REST API (`connections/nextcloud_api.py`)
- `fetch_all_tasks()` — все карточки со всех досок
- `fetch_user_tasks(login)` — карточки конкретного пользователя
- `get_board_title(board_id)` — название доски
- `archive_card(board_id, stack_id, card_id)` — архивация карточки
- `get_comments(card_id)` — комментарии к карточке
- `get_url_attachment(path)` — создание публичной ссылки на вложение

### OCS API
- Используется для создания public share ссылок на вложения
- OAuth Login Flow v2 для авторизации пользователей

### CalDAV (`nc_calendar.py`)
- Библиотека `caldav` для работы с календарём
- `get_calendar(tg_id)` — события пользователя на неделю
- `update_event_partstat()` — обновление RSVP-статуса участника

---

## Отправка сообщений (`sender.py`)
- **Rate limiting**: глобально ~30 msg/s, per-chat ~1 msg/s
- **Auto-HTML**: псевдо-markdown → HTML
  - `*жирный*` → `<b>`
  - `` `код` `` → `<code>`
  - `~зачёркнутый~` → `<s>`
  - `_курсив_` → `<i>`
  - `\\\цитата///` → `<blockquote expandable>`
  - `[имя](tg://user?id=123)` → кликабельная ссылка

---

## Docker
```bash
docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t tg-bot .
docker run --env-file .env tg-bot
```
- Образ: `python:3.11-slim`
- Рабочая директория: `/app/source`
- Entrypoint: `/app/entrypoint.sh` (ожидает MySQL, запускает бота)

---

## Логирование
- `logging_service.send_log()` — отправка в форум-топик (по board_id → thread_id)
- Уведомление о старте в `BOT_START_MESSAGE_TOPIC_ID` с ссылкой на коммит
- Коммит определяется из `GIT_COMMIT` env или `git rev-parse`

---

## Ключевые алгоритмы

### Детекция изменений карточек
1. Получаем все карточки с `fetch_all_tasks()`
2. Сравниваем `etag` с сохранённым в БД
3. Если etag изменился — проверяем поля: stack_id, duedate, title, description
4. `change_description()` — анализ diff описания (добавленные/удалённые пункты, изменённые чекбоксы)
5. Отдельно отслеживаем комментарии (comment_id) и вложения (file_id)

### Напоминания о дедлайнах
1. Расписание: за 24ч (в 10:00 по МСК), в момент дедлайна
2. После просрочки — повтор каждые `DEADLINE_REPEAT_DAYS` дней
3. Если дедлайн перенесён вперёд — сброс отправленных напоминаний

### Перемещение карточек
- Автоперенос в Done-колонку при `done != null`
- Кнопки ⬅/➡ для ручного перемещения
- Использует PUT `/boards/{}/stacks/{}/cards/{}/reorder`

---

## Зависимости
```
pyTelegramBotAPI    # Telegram Bot API
requests            # HTTP-клиент
mysql-connector     # MySQL-драйвер
SQLAlchemy + alembic # ORM и миграции
caldav              # CalDAV-клиент
icalendar           # Парсинг iCal
python-dotenv       # .env файлы
```

---

## Типичные проблемы

1. **Не приходят уведомления** — проверить `EXCLUDED_CARD_IDS`, `QUIET_HOURS`, права сервисного пользователя
2. **Ошибки CalDAV** — проверить `WEB_CALDAV_URL`, права доступа к календарям
3. **OAuth не работает** — проверить `WEB_APP_URL`, что NC отдаёт Login Flow v2
4. **Логи не в том топике** — использовать `/setboardtopic` для привязки

---

## Ответы на комментарии карточек Deck
Бот умеет отвечать на карточки Deck прямо из Telegram:
- Пользователь отвечает реплаем на сообщение бота о карточке
- Бот извлекает `card_id` из URL в кнопке сообщения
- Создаёт комментарий через OCS API от имени пользователя (используя его `nc_token`)
- Ставит реакцию 🙏 при успехе

---

*Документация актуальна для ветки: main*
