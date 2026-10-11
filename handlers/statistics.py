from telebot import types

from bot import bot

from database import (
    get_user,
    get_global_stats,
    complete_verification
)

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK
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

        valid_statuses = (
            "member",
            "administrator",
            "creator"
        )

        return (
            group_member.status in valid_statuses
            and channel_member.status in valid_statuses
        )

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


def show_statistics(message):
    user_id = message.from_user.id

    user = get_user(user_id)

    if not user:
        bot.reply_to(
            message,
            "Pehle /start karke account register karo."
        )
        return

    if not check_membership(user_id):
        bot.send_message(
            message.chat.id,
            "🔐 Statistics dekhne ke liye pehle "
            "group aur channel dono join karo.",
            reply_markup=join_keyboard()
        )
        return

    complete_verification(user_id)

    stats = get_global_stats()

    text = (
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Total Registered Users: "
        f"<b>{stats['total_users']}</b>\n\n"
        f"🎯 Total Successful Referrals: "
        f"<b>{stats['total_referrals']}</b>\n\n"
        f"🪙 Total Coins Spent: "
        f"<b>{stats['total_coins_spent']}</b>"
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔄 Refresh Statistics",
            callback_data="refresh_statistics"
        )
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.message_handler(commands=["stats"])
def statistics_command(message):
    show_statistics(message)


@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() == "📊 Statistics"
    )
)
def statistics_button(message):
    show_statistics(message)


@bot.callback_query_handler(
    func=lambda call: call.data == "refresh_statistics"
)
def refresh_statistics_callback(call):
    user_id = call.from_user.id

    if not check_membership(user_id):
        bot.answer_callback_query(
            call.id,
            "Pehle group aur channel join karo!",
            show_alert=True
        )
        return

    if not get_user(user_id):
        bot.answer_callback_query(
            call.id,
            "Pehle /start karo!",
            show_alert=True
        )
        return

    complete_verification(user_id)

    stats = get_global_stats()

    text = (
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Total Registered Users: "
        f"<b>{stats['total_users']}</b>\n\n"
        f"🎯 Total Successful Referrals: "
        f"<b>{stats['total_referrals']}</b>\n\n"
        f"🪙 Total Coins Spent: "
        f"<b>{stats['total_coins_spent']}</b>"
    )

    try:
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=call.message.reply_markup,
            parse_mode="HTML"
        )

        bot.answer_callback_query(
            call.id,
            "Statistics refreshed!"
        )

    except Exception:
        bot.answer_callback_query(
            call.id,
            "Statistics already up to date."
        )
