import requests
from requests.auth import HTTPBasicAuth
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from source.connections.bot_factory import bot
from source.db.repos.users import delete_login_token, get_token, save_login_to_db_with_token, get_email_by_tg_id
from source.config import BASE_URL, USERNAME, PASSWORD, HEADERS, WEB_APP_URL
from source.connections.sender import send_message_limited
from source.nc_calendar import update_event_partstat
from source.db.repos.caldav_calendar import get_name_by_id

@bot.callback_query_handler(func=lambda call: call.data.startswith("move:"))
def handle_card_move(call):
    """
    Перемещение карточки из одной колонки в другую
    """
    _, board_id, current_stack_id, card_id, new_stack_id = call.data.split(":")
    board_id = int(board_id)
    current_stack_id = int(current_stack_id)
    card_id = int(card_id)
    new_stack_id = int(new_stack_id)
    all_stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS,
                                   auth=HTTPBasicAuth(USERNAME, PASSWORD))
    all_stacks_resp.raise_for_status()
    all_stacks = sorted(all_stacks_resp.json(), key=lambda s: s['order'])
    new_stack_data = next(s for s in all_stacks if s['id'] == new_stack_id)
    position = len(new_stack_data.get("cards", []))
    reorder_url = f"{BASE_URL}/boards/{board_id}/stacks/{new_stack_id}/cards/{card_id}/reorder"
    payload = {"stackId": new_stack_id, "order": position}
    move_resp = requests.put(reorder_url, headers=HEADERS, auth=HTTPBasicAuth(USERNAME, PASSWORD), json=payload)
    if move_resp.status_code not in (200, 204):
        bot.answer_callback_query(call.id, f"Ошибка API ({move_resp.status_code})")
        return
    updated_stacks_resp = requests.get(f"{BASE_URL}/boards/{board_id}/stacks?details=true", headers=HEADERS,
                                       auth=HTTPBasicAuth(USERNAME, PASSWORD))
    updated_stacks_resp.raise_for_status()
    updated_stacks = sorted(updated_stacks_resp.json(), key=lambda s: s['order'])
    new_idx = next(idx for idx, s in enumerate(updated_stacks) if s['id'] == new_stack_id)
    new_kb = InlineKeyboardMarkup()
    if new_idx > 0:
        prev_stack = updated_stacks[new_idx - 1]
        new_kb.add(InlineKeyboardButton(
            text=f"⬅ {prev_stack['title']}",
            callback_data=f"move:{board_id}:{new_stack_id}:{card_id}:{prev_stack['id']}"
        ))
    if new_idx < len(updated_stacks) - 1:
        next_stack = updated_stacks[new_idx + 1]
        new_kb.add(InlineKeyboardButton(
            text=f"➡ {next_stack['title']}",
            callback_data=f"move:{board_id}:{new_stack_id}:{card_id}:{next_stack['id']}"
        ))
    bot.answer_callback_query(call.id, "Перемещено")
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=new_kb)

@bot.callback_query_handler(func=lambda call: call.data == "check")
def check_login(call):
    poll_token = get_token(call.from_user.id)
    endpoint = WEB_APP_URL + "/login/v2/poll"
    headers = {
        'User-Agent': 'ITMOCraftBot',
        'Accept': 'application/json'
    }
    try:
        response = requests.post(endpoint, data={'token': poll_token}, headers=headers)
        response.raise_for_status()
        if response.status_code == 404:
            bot.answer_callback_query(call.id, "Вы еще не подтвердили вход в браузере!", show_alert=True)
        elif response.status_code == 200:
            auth_data = response.json()
            nc_login = auth_data['loginName']
            nc_token = auth_data['appPassword']
            headers_get_info = {
                'OCS-APIRequest': 'true',
                'Accept': 'application/json'
            }
            delete_login_token(call.from_user.id)


            user_url = WEB_APP_URL + "/ocs/v2.php/cloud/user"

            user_response = requests.get(
                user_url,
                auth=(nc_login, nc_token),
                headers=headers_get_info
            )

            user_response.raise_for_status()

            data = user_response.json()
            email = data.get("ocs", {}).get("data", {}).get("email")
            nc_login = data.get("ocs", {}).get("data", {}).get("id")
            save_login_to_db_with_token(call.from_user.id, nc_login, email, nc_token)
            bot.edit_message_text(f"✅ Успешно! Аккаунт {nc_login} привязан.",
                                  call.message.chat.id,
                                  call.message.message_id)

        else:
            send_message_limited(call.message.chat.id, "Произошла ошибка или срок действия ссылки истек.")

    except Exception as e:
        bot.answer_callback_query(call.id, "Произошла ошибка или срок действия ссылки истек.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith('cal_'))
def handle_cal(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split('_', 3)
    if len(parts) < 3:
        return

    action = parts[1]  # ACCEPTED, DECLINED, TENTATIVE
    short_id = parts[2]
    status = parts[3]  # ACCEPTED, DECLINED, TENTATIVE

    if action == status:
        return

    event_url = get_name_by_id(short_id)
    if not event_url:
        return

    user_email = get_email_by_tg_id(call.from_user.id)

    if not user_email:
        send_message_limited(call.message.chat.id, "Не удалось найти ваш email в системе.")
        return

    success = update_event_partstat(event_url, user_email, action)

    if success:
        status_ru = {"ACCEPTED": "✅ Принято", "DECLINED": "❌ Отклонено", "TENTATIVE": "❓ Под вопросом"}
        markup = call.message.reply_markup
        for row in markup.keyboard:
            for button in row:
                btn_parts = button.callback_data.split('_')
                btn_action = btn_parts[1]

                if btn_action == action:
                    button.style = "success"
                else:
                    button.style = None

                button.callback_data = f"cal_{btn_action}_{short_id}_{action}"


        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup = markup
        )
        send_message_limited(call.message.chat.id, f"Ваш статус изменен на: {status_ru.get(action)}")
    else:
        send_message_limited(call.message.chat.id, "Произошла ошибка при обновлении статуса в календаре.")