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


def _get_link_state(user_id):
    """Return active links and the user's unlocked link IDs in bulk."""
    links = get_active_links()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT link_id FROM unlocked_links WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    unlocked_ids = {int(row["link_id"]) for row in rows}
    return links, unlocked_ids


def show_links(chat_id, user_id, notice=None):
    """Show status only; unlocking is done by the reply-keyboard button."""
    links, unlocked_ids = _get_link_state(user_id)
    if not links:
        text = "📭 No links are available at the moment."
        if notice:
            text = notice + "\n\n" + text
        bot.send_message(chat_id, text)
        return

    total = len(links)
    unlocked_count = sum(1 for link in links if int(link["id"]) in unlocked_ids)
    remaining = total - unlocked_count
    text = (
        "🔓 <b>OPEN LINKS</b>\n\n"
        f"📚 Total Available Links: <b>{total}</b>\n"
        f"✅ Links Unlocked by You: <b>{unlocked_count}</b>\n"
        f"🔒 Links Remaining: <b>{remaining}</b>\n\n"
    )
    if remaining:
        text += f"💰 Unlock Cost: <b>{LINK_UNLOCK_COST} Coin(s)</b>\n\nTap <b>🔓 Open Links</b> on the keyboard to unlock your next link."
    else:
        text += "🎉 You have unlocked all available links!"
    if notice:
        text = notice + "\n\n" + text
    bot.send_message(chat_id, text, parse_mode="HTML")


def open_links(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not get_user(user_id):
        bot.reply_to(message, "Please use /start first to register your account.")
        return

    if not check_membership(user_id):
        bot.send_message(
            chat_id,
            "🔐 Please join both the group and the channel to access Open Links.",
            reply_markup=join_keyboard(),
        )
        return

    verification = complete_verification(user_id)
    if not verification["success"]:
        bot.send_message(chat_id, "Verification is not complete. Please try /start again.")
        return

    links, unlocked_ids = _get_link_state(user_id)
    if not links:
        bot.send_message(chat_id, "📭 No links are available at the moment.")
        return

    # The reply-keyboard button itself unlocks the next locked link.
    next_link = next(
        (link for link in links if int(link["id"]) not in unlocked_ids),
        None,
    )
    if next_link is None:
        show_links(chat_id, user_id)
        return

    result = unlock_link(user_id, int(next_link["id"]))
    if not result.get("success"):
        reason = result.get("reason")
        if reason == "insufficient_coins":
            user = get_user(user_id) or {}
            bot.send_message(
                chat_id,
                f"❌ Not enough coins to unlock the next link. Your balance: {user.get('coins_balance', 0)} coins.",
            )
        elif reason == "user_not_verified":
            bot.send_message(chat_id, "Please complete verification first using /start.")
        else:
            bot.send_message(chat_id, "❌ This link is currently unavailable. Please try again.")
        return

    # Recalculate counts after unlocking; send one message only, with a URL button.
    links, unlocked_ids = _get_link_state(user_id)
    total = len(links)
    unlocked_count = sum(1 for link in links if int(link["id"]) in unlocked_ids)
    remaining = total - unlocked_count
    link_number = next(
        (number for number, link in enumerate(links, start=1)
         if int(link["id"]) == int(next_link["id"])),
        None,
    )
    text = (
        f"✅ <b>Link #{link_number} unlocked!</b>\n\n"
        f"📚 Total Available Links: <b>{total}</b>\n"
        f"✅ Links Unlocked by You: <b>{unlocked_count}</b>\n"
        f"🔒 Links Remaining: <b>{remaining}</b>\n"
        f"💰 Unlock Cost: <b>{LINK_UNLOCK_COST} Coin(s)</b>\n\n"
        "Open this link below. To get the next link, tap <b>🔓 Open Links</b> on the keyboard again."
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔗 Open Link", url=result["url"]))
    bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")


@bot.message_handler(commands=["links"])
def links_command(message):
    open_links(message)


@bot.message_handler(func=lambda message: message.text is not None and message.text.strip() == "🔓 Open Links")
def links_button(message):
    open_links(message)


@bot.callback_query_handler(func=lambda call: call.data is not None and call.data.startswith("unlock_"))
def unlock_link_callback(call):
    # Compatibility for old inline unlock buttons sent before this update.
    bot.answer_callback_query(
        call.id,
        "Please use the 🔓 Open Links keyboard button to get your next link.",
        show_alert=True,
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_to_links")
def back_to_links_callback(call):
    bot.answer_callback_query(call.id)
    show_links(call.message.chat.id, call.from_user.id)
