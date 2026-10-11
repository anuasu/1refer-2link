import telebot
from telebot import types

from bot import bot

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
    WELCOME_BONUS
)

from database import (
    register_user,
    get_user,
    complete_verification
)


def check_membership(user_id):
    try:
        group_member = bot.get_chat_member(
            GROUP_ID,
            user_id
        )

        channel_member = bot.get_chat_member(
            CHANNEL_ID,
            user_id
        )

        valid_statuses = [
            "member",
            "administrator",
            "creator"
        ]

        group_joined = (
            group_member.status in valid_statuses
        )

        channel_joined = (
            channel_member.status in valid_statuses
        )

        return group_joined and channel_joined

    except Exception:
        return False


def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Join Group",
            url=GROUP_INVITE_LINK
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📣 Join Channel",
            url=CHANNEL_INVITE_LINK
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "✅ Check Join",
            callback_data="check_join"
        )
    )

    return keyboard


def main_menu():
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row(
        "📊 Statistics",
        "👥 Refer & Earn"
    )

    keyboard.row(
        "🔓 Open Links"
    )

    return keyboard


def send_join_message(chat_id):
    bot.send_message(
        chat_id,
        "🔐 <b>Join Required</b>\n\n"
        "Bot use karne ke liye hamara private group "
        "aur private channel dono join karo.\n\n"
        "Join karne ke baad neeche Check Join button dabao.",
        reply_markup=join_keyboard(),
        parse_mode="HTML"
    )


def send_welcome(chat_id, first_name, bonus=0):
    text = (
        f"👋 Welcome, <b>{first_name}</b>!\n\n"
        "🎉 Aapka verification complete ho gaya hai.\n\n"
    )

    if bonus > 0:
        text += (
            f"🎁 Welcome Bonus: <b>+{bonus} Coins</b>\n\n"
        )

    text += "Neeche se apna option select karo. ❤️🤍"

    bot.send_message(
        chat_id,
        text,
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    username = message.from_user.username or ""

    referral_id = None
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1:
        referral_code = parts[1].strip()

        if referral_code.isdigit():
            referral_id = int(referral_code)

            if referral_id == user_id:
                referral_id = None

    existing_user = get_user(user_id)

    register_user(
        user_id=user_id,
        first_name=first_name,
        username=username,
        referred_by=referral_id
    )

    if not check_membership(user_id):
        send_join_message(message.chat.id)
        return

    result = complete_verification(user_id)

    if not result["success"]:
        bot.send_message(
            message.chat.id,
            "❌ Verification complete nahi ho paya.\n"
            "Please dobara /start try karo."
        )
        return

    if result["welcome_bonus"] > 0:
        send_welcome(
            message.chat.id,
            first_name,
            result["welcome_bonus"]
        )

    elif existing_user:
        bot.send_message(
            message.chat.id,
            "❤️🤍 Welcome back!\n\n"
            "Neeche se apna option select karo.",
            reply_markup=main_menu()
        )

    else:
        send_welcome(
            message.chat.id,
            first_name
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "check_join"
)
def check_join_callback(call):
    user_id = call.from_user.id

    if not check_membership(user_id):
        bot.answer_callback_query(
            call.id,
            "Pehle group aur channel dono join karo!",
            show_alert=True
        )
        return

    user = get_user(user_id)

    if not user:
        bot.answer_callback_query(
            call.id,
            "Pehle /start karo!",
            show_alert=True
        )
        return

    result = complete_verification(user_id)

    if not result["success"]:
        bot.answer_callback_query(
            call.id,
            "Verification failed. Dobara try karo.",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Verification successful!"
    )

    try:
        bot.delete_message(
            call.message.chat.id,
            call.message.message_id
        )
    except Exception:
        pass

    first_name = call.from_user.first_name or "User"

    send_welcome(
        call.message.chat.id,
        first_name,
        result["welcome_bonus"]
      )
