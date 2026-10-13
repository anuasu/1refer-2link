import html

from telebot import types

from bot import bot

from database import (
    get_user,
    get_global_stats,
    get_top_users,
    complete_verification,
)

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
)


# =========================================================
# MEMBERSHIP CHECK
# =========================================================

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
            "creator",
        )

        return (
            group_member.status in valid_statuses
            and channel_member.status in valid_statuses
        )

    except Exception as error:
        print(f"Membership check error: {error}")
        return False


# =========================================================
# JOIN KEYBOARD
# =========================================================

def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Join Group",
            url=GROUP_INVITE_LINK
        ),
        types.InlineKeyboardButton(
            "📣 Join Channel",
            url=CHANNEL_INVITE_LINK
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Check Membership",
            callback_data="check_join"
        )
    )

    return keyboard


# =========================================================
# STATISTICS KEYBOARD
# =========================================================

def statistics_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔄 Refresh Statistics",
            callback_data="refresh_statistics"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🏆 Top 50 Leaderboard",
            callback_data="top50_leaderboard"
        )
    )

    return keyboard


# =========================================================
# SHOW GLOBAL STATISTICS
# =========================================================

def show_statistics(message):
    user_id = message.from_user.id

    user = get_user(user_id)

    if not user:
        bot.send_message(
            message.chat.id,
            "❌ Please start the bot first using /start."
        )
        return

    if not check_membership(user_id):
        bot.send_message(
            message.chat.id,
            (
                "⚠️ Please join both our group and channel "
                "to view statistics."
            ),
            reply_markup=join_keyboard()
        )
        return

    complete_verification(user_id)

    stats = get_global_stats()

    text = (
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Total Users: <b>{stats['total_users']:,}</b>\n"
        f"🤝 Successful Referrals: "
        f"<b>{stats['total_referrals']:,}</b>\n"
        f"🪙 Total Coins Spent: "
        f"<b>{stats['total_coins_spent']:,}</b>\n\n"
        "🏆 Tap below to view the Top 50 users."
    )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="HTML",
        reply_markup=statistics_keyboard()
    )


# =========================================================
# TOP 50 LEADERBOARD
# =========================================================

def show_top50(chat_id, message_id=None):
    users = get_top_users(50)

    if not users:
        text = (
            "🏆 <b>TOP 50 LEADERBOARD</b>\n\n"
            "No users are currently available on the leaderboard."
        )

    else:
        lines = [
            "🏆 <b>TOP 50 LEADERBOARD</b>",
            "",
            "📊 Ranking: Highest Current Coin Balance",
            "",
        ]

        for rank, user in enumerate(users, start=1):
            name = html.escape(
                user.get("first_name") or "Unknown"
            )

            username_value = user.get("username") or ""

            username = (
                "@" + html.escape(username_value.lstrip("@"))
                if username_value.strip()
                else "No Username"
            )

            user_id = user["user_id"]
            coins = user["coins_balance"]
            referrals = user["referral_count"]

            lines.append(
                f"<b>#{rank} {name}</b>\n"
                f"👤 Username: {username}\n"
                f"🆔 Chat ID: <code>{user_id}</code>\n"
                f"🪙 Coins: <b>{coins:,}</b>\n"
                f"👥 Referrals: <b>{referrals:,}</b>"
            )

            lines.append("")

        text = "\n".join(lines)

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="top50_leaderboard"
        ),
        types.InlineKeyboardButton(
            "🔙 Back to Statistics",
            callback_data="back_to_statistics"
        )
    )

    if message_id:
        try:
            bot.edit_message_text(
                text,
                chat_id,
                message_id,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return

        except Exception as error:
            print(f"Leaderboard edit error: {error}")

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# COMMAND HANDLERS
# =========================================================

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


# =========================================================
# CALLBACK: REFRESH STATISTICS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "refresh_statistics"
)
def refresh_statistics_callback(call):
    try:
        bot.answer_callback_query(call.id)

        user_id = call.from_user.id

        if not check_membership(user_id):
            bot.send_message(
                call.message.chat.id,
                (
                    "⚠️ Please join both our group and channel "
                    "to continue."
                ),
                reply_markup=join_keyboard()
            )
            return

        complete_verification(user_id)

        stats = get_global_stats()

        text = (
            "📊 <b>BOT STATISTICS</b>\n\n"
            f"👥 Total Users: <b>{stats['total_users']:,}</b>\n"
            f"🤝 Successful Referrals: "
            f"<b>{stats['total_referrals']:,}</b>\n"
            f"🪙 Total Coins Spent: "
            f"<b>{stats['total_coins_spent']:,}</b>\n\n"
            "🏆 Tap below to view the Top 50 users."
        )

        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=statistics_keyboard()
        )

    except Exception as error:
        print(f"Statistics refresh error: {error}")


# =========================================================
# CALLBACK: OPEN TOP 50
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "top50_leaderboard"
)
def top50_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not check_membership(call.from_user.id):
            bot.send_message(
                call.message.chat.id,
                (
                    "⚠️ Please join both our group and channel "
                    "to continue."
                ),
                reply_markup=join_keyboard()
            )
            return

        complete_verification(call.from_user.id)

        show_top50(
            call.message.chat.id,
            call.message.message_id
        )

    except Exception as error:
        print(f"Top 50 callback error: {error}")


# =========================================================
# CALLBACK: BACK TO STATISTICS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "back_to_statistics"
)
def back_to_statistics_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not check_membership(call.from_user.id):
            bot.send_message(
                call.message.chat.id,
                (
                    "⚠️ Please join both our group and channel "
                    "to continue."
                ),
                reply_markup=join_keyboard()
            )
            return

        complete_verification(call.from_user.id)

        stats = get_global_stats()

        text = (
            "📊 <b>BOT STATISTICS</b>\n\n"
            f"👥 Total Users: <b>{stats['total_users']:,}</b>\n"
            f"🤝 Successful Referrals: "
            f"<b>{stats['total_referrals']:,}</b>\n"
            f"🪙 Total Coins Spent: "
            f"<b>{stats['total_coins_spent']:,}</b>\n\n"
            "🏆 Tap below to view the Top 50 users."
        )

        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=statistics_keyboard()
        )

    except Exception as error:
        print(f"Back to statistics error: {error}")


# =========================================================
# EXISTING CHECK-JOIN CALLBACK
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "check_join"
)
def check_join_callback(call):
    try:
        if check_membership(call.from_user.id):
            complete_verification(call.from_user.id)

            bot.answer_callback_query(
                call.id,
                "✅ Membership verified!",
                show_alert=True
            )

        else:
            bot.answer_callback_query(
                call.id,
                "❌ Please join both the group and channel.",
                show_alert=True
            )

    except Exception as error:
        print(f"Check join error: {error}")
