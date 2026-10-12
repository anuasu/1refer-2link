import html
import logging
import threading

from telebot import types

from bot import bot
from database import (
    get_user,
    redeem_code_for_user,
)

from config import (
    GROUP_ID,
    CHANNEL_ID,
    GROUP_INVITE_LINK,
    CHANNEL_INVITE_LINK,
)

logger = logging.getLogger(__name__)

# Track users currently entering a redeem code
redeem_sessions = set()
session_lock = threading.Lock()


# ==========================================
# KEYBOARDS
# ==========================================

def redeem_back_keyboard():
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )
    keyboard.row("🔙 Back")
    return keyboard


def redeem_inline_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "👥 Join Group",
            url=GROUP_INVITE_LINK
        ),
        types.InlineKeyboardButton(
            "📢 Join Channel",
            url=CHANNEL_INVITE_LINK
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔄 Check Join",
            callback_data="redeem_check_join"
        )
    )

    return keyboard


def is_member(user_id):
    """Check whether the user belongs to the required group and channel."""

    for chat_id in (GROUP_ID, CHANNEL_ID):
        try:
            member = bot.get_chat_member(chat_id, user_id)

            if member.status in ("left", "kicked"):
                return False

        except Exception:
            logger.exception(
                "Membership check failed for user %s in chat %s",
                user_id,
                chat_id
            )
            return False

    return True


def show_redeem_join_prompt(chat_id):
    bot.send_message(
        chat_id,
        "🔒 <b>Join Required</b>\n\n"
        "Redeem code use karne ke liye pehle required "
        "group aur channel join karo.\n\n"
        "Join karne ke baad <b>Check Join</b> dabao.",
        reply_markup=redeem_inline_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# REDEEM CODE BUTTON
# ==========================================

@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() == "🎁 Redeem Code"
    )
)
def redeem_code_button(message):
    user_id = message.from_user.id

    user = get_user(user_id)

    if not user:
        bot.reply_to(
            message,
            "Pehle /start karo, phir redeem code use karna."
        )
        return

    if not is_member(user_id):
        show_redeem_join_prompt(message.chat.id)
        return

    with session_lock:
        redeem_sessions.add(user_id)

    bot.send_message(
        message.chat.id,
        "🎁 <b>Redeem Code</b>\n\n"
        "Apna redeem code bhejo.\n"
        "Code enter karte hi reward tumhare existing "
        "coin balance mein add ho jayega.\n\n"
        "Cancel karne ke liye 🔙 Back dabao.",
        reply_markup=redeem_back_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# CHECK MEMBERSHIP CALLBACK
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_check_join"
)
def redeem_check_join_callback(call):
    user_id = call.from_user.id

    if not is_member(user_id):
        bot.answer_callback_query(
            call.id,
            "Pehle dono required chats join karo.",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Membership verified!"
    )

    try:
        bot.edit_message_text(
            "✅ Membership check successful!\n\n"
            "Ab bot ke menu se 🎁 Redeem Code select karo.",
            call.message.chat.id,
            call.message.message_id
        )
    except Exception:
        pass


# ==========================================
# HANDLE REDEEM INPUT
# ==========================================

@bot.message_handler(
    func=lambda message: (
        message.from_user is not None
        and message.text is not None
        and message.from_user.id in redeem_sessions
    )
)
def process_redeem_code(message):
    user_id = message.from_user.id
    code_input = message.text.strip()

    # Cancel the redeem process
    if code_input in ("🔙 Back", "/cancel"):
        with session_lock:
            redeem_sessions.discard(user_id)

        bot.send_message(
            message.chat.id,
            "Redeem process cancelled.",
            reply_markup=types.ReplyKeyboardRemove()
        )

        bot.send_message(
            message.chat.id,
            "Menu ke liye /start use karo."
        )
        return

    # Ignore unrelated commands
    if code_input.startswith("/"):
        bot.reply_to(
            message,
            "Redeem code bhejo ya cancel karne ke liye 🔙 Back dabao."
        )
        return

    if not is_member(user_id):
        show_redeem_join_prompt(message.chat.id)
        return

    if not code_input or len(code_input) > 100:
        bot.reply_to(
            message,
            "❌ Invalid code. Sahi redeem code enter karo."
        )
        return

    code = code_input.upper()

    try:
        result = redeem_code_for_user(user_id, code)
    except Exception:
        logger.exception(
            "Redeem failed for user %s",
            user_id
        )
        bot.reply_to(
            message,
            "⚠️ Redeem process mein error aaya. Thodi der baad try karo."
        )
        return

    if not isinstance(result, dict):
        bot.reply_to(
            message,
            "❌ Code redeem nahi ho saka. Dobara try karo."
        )
        return

    success = result.get("success", False)

    if not success:
        reason = result.get("reason", "invalid_code")

        errors = {
            "invalid_code": "❌ Ye redeem code exist nahi karta.",
            "inactive_code": "❌ Ye redeem code inactive hai.",
            "expired_code": "⌛ Is redeem code ki expiry ho chuki hai.",
            "already_redeemed": "⚠️ Tum ye code pehle hi redeem kar chuke ho.",
            "limit_reached": "❌ Is code ka redemption limit complete ho gaya.",
            "user_not_found": "Pehle /start karke account register karo.",
            "invalid_expiry": "⌛ Ye redeem code ab valid nahi hai.",
        }

        bot.reply_to(
            message,
            errors.get(
                reason,
                "❌ Code redeem nahi ho saka. Code check karke dobara try karo."
            )
        )
        return

    # Clear session after successful redemption
    with session_lock:
        redeem_sessions.discard(user_id)

    reward = result.get(
        "reward_coins",
        result.get("reward", 0)
    )

    bot.send_message(
        message.chat.id,
        "🎉 <b>Redeem Successful!</b>\n\n"
        f"🎁 Reward: <b>+{html.escape(str(reward))} coins</b>\n"
        "💰 Reward tumhare account mein add kar diya gaya hai.\n\n"
        "Ab tum bot ke doosre features bhi use kar sakte ho.",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
