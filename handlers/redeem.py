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
            "🔄 Check Membership",
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
        "🔒 <b>Membership Required</b>\n\n"
        "To use redeem codes, you must first join both "
        "the required group and channel.\n\n"
        "After joining, press <b>Check Membership</b>.",
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
            "Please use /start to register your account before redeeming a code."
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
        "Please send your redeem code.\n"
        "Once you enter a valid code, the reward will be "
        "added to your existing coin balance.\n\n"
        "Press 🔙 Back to cancel.",
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
            "Please join both required chats first.",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Membership verified!"
    )

    try:
        bot.edit_message_text(
            "✅ Membership verification successful!\n\n"
            "Now select 🎁 Redeem Code from the bot menu.",
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
            "The redemption process has been cancelled.",
            reply_markup=types.ReplyKeyboardRemove()
        )

        bot.send_message(
            message.chat.id,
            "Use /start to return to the main menu."
        )
        return

    # Ignore unrelated commands
    if code_input.startswith("/"):
        bot.reply_to(
            message,
            "Please enter a redeem code or press 🔙 Back to cancel."
        )
        return

    if not is_member(user_id):
        show_redeem_join_prompt(message.chat.id)
        return

    if not code_input or len(code_input) > 100:
        bot.reply_to(
            message,
            "❌ Invalid code. Please enter a valid redeem code."
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
            "⚠️ An error occurred while processing your redemption. Please try again later."
        )
        return

    if not isinstance(result, dict):
        bot.reply_to(
            message,
            "❌ Unable to redeem the code. Please try again."
        )
        return

    success = result.get("success", False)

    if not success:
        reason = result.get("reason", "invalid_code")

        errors = {
            "invalid_code": "❌ This redeem code does not exist.",
            "inactive_code": "❌ This redeem code is inactive.",
            "expired_code": "⌛ This redeem code has expired.",
            "already_redeemed": "⚠️ You have already redeemed this code.",
            "limit_reached": "❌ The redemption limit for this code has been reached.",
            "user_not_found": "Please use /start to register your account first.",
            "invalid_expiry": "⌛ This redeem code is no longer valid.",
        }

        bot.reply_to(
            message,
            errors.get(
                reason,
                "❌ Unable to redeem the code. Please check the code and try again."
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
        "🎉 <b>Redemption Successful!</b>\n\n"
        f"🎁 Reward: <b>+{html.escape(str(reward))} coins</b>\n"
        "💰 The reward has been added to your account.\n\n"
        "You can now explore the other features of the bot.",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
