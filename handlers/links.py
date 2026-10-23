from telebot import types

from bot import bot
from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
    LINK_UNLOCK_COST,
)
from database import (
    get_user,
    complete_verification,
    get_active_links,
    has_unlocked_link,
    unlock_link,
)


# =========================================================
# MEMBERSHIP AND JOIN KEYBOARD
# =========================================================

def check_membership(user_id):
    try:
        group_member = bot.get_chat_member(GROUP_ID, user_id)
        channel_member = bot.get_chat_member(CHANNEL_ID, user_id)
        valid_statuses = ("member", "administrator", "creator")
        return (
            group_member.status in valid_statuses
            and channel_member.status in valid_statuses
        )
    except Exception as error:
        print(f"Membership check error: {error}")
        return False


def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("📢 Join Group", url=GROUP_INVITE_LINK),
        types.InlineKeyboardButton("📣 Join Channel", url=CHANNEL_INVITE_LINK),
    )
    keyboard.row(
        types.InlineKeyboardButton("✅ Check Join", callback_data="check_join")
    )
    return keyboard


# =========================================================
# ACCESS CHECKS
# =========================================================

def verify_link_access(chat_id, user_id):
    if not get_user(user_id):
        bot.send_message(
            chat_id,
            "❌ <b>Registration Required</b>\n\nPlease use /start to register your account first.",
            parse_mode="HTML",
        )
        return False

    if not check_membership(user_id):
        bot.send_message(
            chat_id,
            "🔐 <b>Membership Required</b>\n\nPlease join both the group and channel to access links.",
            reply_markup=join_keyboard(),
            parse_mode="HTML",
        )
        return False

    verification = complete_verification(user_id)
    if not verification or not verification.get("success"):
        bot.send_message(
            chat_id,
            "❌ <b>Verification Incomplete</b>\n\nPlease use /start and complete verification before opening links.",
            parse_mode="HTML",
        )
        return False

    return True


# =========================================================
# LINK DISPLAY
# =========================================================

def send_unlocked_link(chat_id, link_number, result):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔗 Open Link", url=result["url"])
    )

    bot.send_message(
        chat_id,
        (
            "✅ <b>Link Unlocked Successfully!</b>\n\n"
            f"📍 <b>Link:</b> #{link_number}\n"
            f"🪙 <b>Remaining Coins:</b> {result.get('balance', 0)}\n\n"
            "Tap the button below to open your link."
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def open_next_link(chat_id, user_id):
    """Unlock the next available link when the reply-keyboard button is pressed."""
    if not verify_link_access(chat_id, user_id):
        return

    links = get_active_links() or []
    if not links:
        bot.send_message(
            chat_id,
            "📭 <b>No Links Available</b>\n\nPlease check back later.",
            parse_mode="HTML",
        )
        return

    next_link = None
    next_number = None

    for number, link in enumerate(links, start=1):
        if not has_unlocked_link(user_id, int(link["id"])):
            next_link = link
            next_number = number
            break

    if next_link is None:
        bot.send_message(
            chat_id,
            (
                "🎉 <b>All Links Unlocked!</b>\n\n"
                f"🔗 <b>Total Available Links:</b> {len(links)}\n"
                "You have already unlocked every available link."
            ),
            parse_mode="HTML",
        )
        return

    result = unlock_link(user_id, int(next_link["id"]))
    if not result or not result.get("success"):
        reason = result.get("reason") if result else None

        if reason == "insufficient_coins":
            user = get_user(user_id)
            balance = user.get("coins_balance", 0) if isinstance(user, dict) else 0
            bot.send_message(
                chat_id,
                (
                    "❌ <b>Insufficient Coins</b>\n\n"
                    f"💰 <b>Unlock Cost:</b> {LINK_UNLOCK_COST} coin(s)\n"
                    f"🪙 <b>Your Balance:</b> {balance} coins\n\n"
                    "Earn more coins through referrals and daily rewards, then try again."
                ),
                parse_mode="HTML",
            )
        elif reason == "user_not_verified":
            bot.send_message(
                chat_id,
                "❌ Please complete membership verification before unlocking links.",
            )
        else:
            bot.send_message(
                chat_id,
                "❌ This link is currently unavailable. Please try again later.",
            )
        return

    send_unlocked_link(chat_id, next_number, result)


def open_links(message):
    open_next_link(message.chat.id, message.from_user.id)


# =========================================================
# REPLY-KEYBOARD BUTTON AND COMMAND
# =========================================================

@bot.message_handler(commands=["links"])
def links_command(message):
    open_links(message)


@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() in ("🔓 Open Links", "🔓 Open Link")
    )
)
def links_button(message):
    open_links(message)


# =========================================================
# BACKWARD COMPATIBILITY FOR OLD INLINE UNLOCK BUTTONS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data is not None and call.data.startswith("unlock_")
)
def unlock_link_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if not get_user(user_id):
        bot.answer_callback_query(call.id, "Please use /start first!", show_alert=True)
        return

    if not check_membership(user_id):
        bot.answer_callback_query(
            call.id,
            "Please join both the group and channel first!",
            show_alert=True,
        )
        bot.send_message(
            chat_id,
            "🔐 Please join both the group and channel to unlock links.",
            reply_markup=join_keyboard(),
        )
        return

    verification = complete_verification(user_id)
    if not verification or not verification.get("success"):
        bot.answer_callback_query(call.id, "Verification is incomplete!", show_alert=True)
        return

    try:
        link_id = int(call.data.split("_", 1)[1])
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "Invalid link!", show_alert=True)
        return

    links = get_active_links() or []
    link_number = next(
        (number for number, item in enumerate(links, start=1)
         if int(item["id"]) == link_id),
        None,
    )

    result = unlock_link(user_id, link_id)
    if not result or not result.get("success"):
        reason = result.get("reason") if result else None
        if reason == "insufficient_coins":
            user = get_user(user_id)
            balance = user.get("coins_balance", 0) if isinstance(user, dict) else 0
            message = f"Insufficient coins! Your balance: {balance}"
        elif reason == "user_not_verified":
            message = "Please complete verification first!"
        else:
            message = "This link is not available."
        bot.answer_callback_query(call.id, message, show_alert=True)
        return

    bot.answer_callback_query(
        call.id,
        "Already unlocked!" if result.get("already_unlocked") else "Link unlocked!",
    )
    send_unlocked_link(chat_id, link_number or 1, result)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_links")
def back_to_links_callback(call):
    bot.answer_callback_query(call.id)
    open_next_link(call.message.chat.id, call.from_user.id)
