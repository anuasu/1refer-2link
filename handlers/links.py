from telebot import types
from bot import bot
from config import GROUP_ID, GROUP_INVITE_LINK, CHANNEL_ID, CHANNEL_INVITE_LINK, LINK_UNLOCK_COST
from database import get_user, complete_verification, get_active_links, has_unlocked_link, unlock_link, get_connection


def check_membership(user_id):
    try:
        group_member = bot.get_chat_member(GROUP_ID, user_id)
        channel_member = bot.get_chat_member(CHANNEL_ID, user_id)
        valid_statuses = ("member", "administrator", "creator")
        return group_member.status in valid_statuses and channel_member.status in valid_statuses
    except Exception:
        return False


def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("📢 Join Group", url=GROUP_INVITE_LINK))
    keyboard.row(types.InlineKeyboardButton("📣 Join Channel", url=CHANNEL_INVITE_LINK))
    keyboard.row(types.InlineKeyboardButton("✅ Check Join", callback_data="check_join"))
    return keyboard


def show_links(chat_id, user_id, notice=None):
    # Fetch links and this user's unlock history in bulk, rather than
    # opening a separate SQLite connection for every link.
    links = get_active_links()

    if not links:
        text = "📭 No links are available at the moment."
        if notice:
            text = notice + "\n\n" + text
        bot.send_message(chat_id, text)
        return

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT link_id FROM unlocked_links WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    unlocked_ids = {int(row["link_id"]) for row in rows}

    unlocked_count = sum(1 for link in links if int(link["id"]) in unlocked_ids)
    total_links = len(links)
    remaining_count = total_links - unlocked_count

    text = (
        "🔓 <b>OPEN LINKS</b>\n\n"
        f"📚 Total Available Links: <b>{total_links}</b>\n"
        f"✅ Links Unlocked by You: <b>{unlocked_count}</b>\n"
        f"🔒 Links Remaining: <b>{remaining_count}</b>\n"
    )

    if remaining_count == 0:
        text += "\n🎉 You have unlocked all available links!"
        if notice:
            text = notice + "\n\n" + text
        bot.send_message(chat_id, text, parse_mode="HTML")
        return

    next_link = None
    next_number = None
    for number, link in enumerate(links, start=1):
        if int(link["id"]) not in unlocked_ids:
            next_link = link
            next_number = number
            break

    text += (
        f"\n📍 Next Link: <b>#{next_number}</b>\n"
        f"💰 Unlock Cost: <b>{LINK_UNLOCK_COST} Coins</b>\n\n"
        "Tap the button below to unlock the next link."
    )
    if notice:
        text = notice + "\n\n" + text

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        f"🔓 Open Link #{next_number}",
        callback_data=f"unlock_{next_link['id']}"
    ))
    bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")


def open_links(message):
    user_id = message.from_user.id

    if not get_user(user_id):
        bot.reply_to(message,"Please use /start first to register your account.")
        return

    if not check_membership(user_id):
        bot.send_message(
            message.chat.id,
           "🔐 Please join both the group and the channel to access Open Links.",
            reply_markup=join_keyboard()
        )
        return

    verification = complete_verification(user_id)

    if not verification["success"]:
        bot.send_message(message.chat.id, "Verification is not complete please try /start again")
        return

    show_links(message.chat.id, user_id)


@bot.message_handler(commands=["links"])
def links_command(message):
    open_links(message)


@bot.message_handler(func=lambda message: message.text is not None and message.text.strip() == "🔓 Open Links")
def links_button(message):
    open_links(message)


@bot.callback_query_handler(func=lambda call: call.data is not None and call.data.startswith("unlock_"))
def unlock_link_callback(call):
    user_id = call.from_user.id

    if not get_user(user_id):
        bot.answer_callback_query(call.id, "Please use /start first!", show_alert=True)
        return

    if not check_membership(user_id):
        bot.answer_callback_query(call.id, "Please join both the group and the channel first!", show_alert=True)
        bot.send_message(
            call.message.chat.id,
            "🔐 Please join both the group and the channel to unlock this link.",
            reply_markup=join_keyboard()
        )
        return

    verification = complete_verification(user_id)

    if not verification["success"]:
        bot.answer_callback_query(call.id, "Verification is not complete!", show_alert=True)
        return

    try:
        link_id = int(call.data.split("_", 1)[1])
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "Invalid link!", show_alert=True)
        return

    result = unlock_link(user_id, link_id)

    if not result["success"]:
        reason = result.get("reason")

        if reason == "insufficient_coins":
            error_message = f"Insufficient coins! Balance: {get_user(user_id)['coins_balance']}"
        elif reason == "user_not_verified":
            error_message = "Please complete the verification first!"
        else:
            error_message = "This link is not available."

        bot.answer_callback_query(call.id, error_message, show_alert=True)
        return

    bot.answer_callback_query(
        call.id,
        "Already unlocked!" if result["already_unlocked"] else "Link unlocked successfully!"
    )

    links = get_active_links()
    current_number = next(
        (
            number
            for number, link in enumerate(links, start=1)
            if int(link["id"]) == link_id
        ),
        None
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔗 Open Link", url=result["url"])
    )

    bot.send_message(
        call.message.chat.id,
        "✅ <b>Link Unlocked!</b>\n\n"
        + (f"📍 Link: <b>#{current_number}</b>\n" if current_number else "")
        + f"💰 Remaining Coins: <b>{result['balance']}</b>\n\n"
       "Open the link using the button below.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    show_links(
        call.message.chat.id,
        user_id,
        notice=f"✅ Link #{current_number} has been unlocked!" if current_number else None
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_to_links")
def back_to_links_callback(call):
    user_id = call.from_user.id

    if not get_user(user_id):
        bot.answer_callback_query(call.id, "Please use /start first!", show_alert=True)
        return

    if not check_membership(user_id):
        bot.answer_callback_query(call.id, "Please join the group and channel first!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    show_links(call.message.chat.id, user_id)
