import html
import logging

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
# SETTINGS
# =========================================================

logger = logging.getLogger(__name__)

LEADERBOARD_LIMIT = 50
LEADERBOARD_PAGE_SIZE = 25


# =========================================================
# MEMBERSHIP CHECK
# =========================================================

def check_membership(user_id):
    try:
        valid_statuses = (
            "member",
            "administrator",
            "creator",
        )

        group_member = bot.get_chat_member(
            GROUP_ID,
            user_id,
        )

        channel_member = bot.get_chat_member(
            CHANNEL_ID,
            user_id,
        )

        return (
            group_member.status in valid_statuses
            and channel_member.status in valid_statuses
        )

    except Exception:
        logger.exception(
            "Membership check failed for user %s",
            user_id,
        )
        return False


# =========================================================
# JOIN KEYBOARD
# =========================================================

def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Join Group",
            url=GROUP_INVITE_LINK,
        ),
        types.InlineKeyboardButton(
            "📣 Join Channel",
            url=CHANNEL_INVITE_LINK,
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Check Membership",
            callback_data="check_join",
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
            callback_data="refresh_statistics",
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🏆 Top 50 Leaderboard",
            callback_data="top50_leaderboard",
        )
    )

    return keyboard


# =========================================================
# BUILD STATISTICS TEXT
# =========================================================

def build_statistics_text():
    stats = get_global_stats() or {}

    total_users = int(
        stats.get("total_users", 0) or 0
    )

    total_referrals = int(
        stats.get("total_referrals", 0) or 0
    )

    total_coins_spent = int(
        stats.get("total_coins_spent", 0) or 0
    )

    return (
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Total Users: <b>{total_users:,}</b>\n"
        f"🤝 Successful Referrals: "
        f"<b>{total_referrals:,}</b>\n"
        f"🪙 Total Coins Spent: "
        f"<b>{total_coins_spent:,}</b>\n\n"
        "🏆 Tap below to view the Top 50 users."
    )


# =========================================================
# SHOW STATISTICS
# =========================================================

def show_statistics(message):
    user_id = message.from_user.id

    try:
        user = get_user(user_id)

        if not user:
            bot.send_message(
                message.chat.id,
                "❌ Please start the bot first using /start.",
            )
            return

        if not check_membership(user_id):
            bot.send_message(
                message.chat.id,
                (
                    "⚠️ Please join both our group and channel "
                    "to view statistics."
                ),
                reply_markup=join_keyboard(),
            )
            return

        complete_verification(user_id)

        bot.send_message(
            message.chat.id,
            build_statistics_text(),
            parse_mode="HTML",
            reply_markup=statistics_keyboard(),
        )

    except Exception:
        logger.exception("Could not display statistics")

        bot.send_message(
            message.chat.id,
            "❌ Statistics load nahi ho paayi. Please try again.",
        )


# =========================================================
# LEADERBOARD NAVIGATION KEYBOARD
# =========================================================

def leaderboard_keyboard(page, total_users):
    keyboard = types.InlineKeyboardMarkup()

    total_pages = max(
        1,
        (total_users + LEADERBOARD_PAGE_SIZE - 1)
        // LEADERBOARD_PAGE_SIZE,
    )

    navigation_buttons = []

    if page > 0:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                "⬅️ Back",
                callback_data=f"top50_page:{page - 1}",
            )
        )

    if page < total_pages - 1:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                "➡️ Next",
                callback_data=f"top50_page:{page + 1}",
            )
        )

    if navigation_buttons:
        keyboard.row(*navigation_buttons)

    keyboard.row(
        types.InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="top50_leaderboard",
        ),
        types.InlineKeyboardButton(
            "🔙 Statistics",
            callback_data="back_to_statistics",
        ),
    )

    return keyboard


# =========================================================
# SHOW TOP 50 LEADERBOARD
# =========================================================

def show_top50(chat_id, message_id=None, page=0):
    try:
        # Fetch the top 50 users from the database.
        users = get_top_users(LEADERBOARD_LIMIT) or []

        users = list(users)[:LEADERBOARD_LIMIT]

        total_users = len(users)

        total_pages = max(
            1,
            (
                total_users + LEADERBOARD_PAGE_SIZE - 1
            ) // LEADERBOARD_PAGE_SIZE,
        )

        # Keep the page number within the valid range.
        page = max(0, min(int(page), total_pages - 1))

        start_index = page * LEADERBOARD_PAGE_SIZE
        end_index = min(
            start_index + LEADERBOARD_PAGE_SIZE,
            total_users,
        )

        page_users = users[start_index:end_index]

        # -------------------------------------------------
        # EMPTY LEADERBOARD
        # -------------------------------------------------

        if not users:
            text = (
                "🏆 <b>TOP 50 LEADERBOARD</b>\n\n"
                "No users are currently available "
                "on the leaderboard."
            )

        # -------------------------------------------------
        # BUILD CURRENT PAGE
        # -------------------------------------------------

        else:
            lines = [
                "🏆 <b>TOP 50 LEADERBOARD</b>",
                "",
                "📊 Ranking: Highest Current Coin Balance",
                f"📄 Page: {page + 1}/{total_pages}",
                f"👥 Showing users: #{start_index + 1}"
                f"–#{end_index}",
                "",
                "━━━━━━━━━━━━━━━━━━",
                "",
            ]

            for rank, user in enumerate(
                page_users,
                start=start_index + 1,
            ):
                first_name = html.escape(
                    str(user.get("first_name") or "Unknown")
                )

                username_value = str(
                    user.get("username") or ""
                ).strip()

                if username_value:
                    username = "@" + html.escape(
                        username_value.lstrip("@")
                    )
                else:
                    username = "No Username"

                user_id = int(
                    user.get("user_id", 0) or 0
                )

                coins = int(
                    user.get("coins_balance", 0) or 0
                )

                referrals = int(
                    user.get("referral_count", 0) or 0
                )

                lines.extend(
                    [
                        f"<b>#{rank} {first_name}</b>",
                        f"👤 Username: {username}",
                        f"🆔 Chat ID: <code>{user_id}</code>",
                        f"🪙 Coins: <b>{coins:,}</b>",
                        f"👥 Referrals: <b>{referrals:,}</b>",
                        "",
                    ]
                )

            lines.extend(
                [
                    "━━━━━━━━━━━━━━━━━━",
                    "",
                    f"📄 Page {page + 1} of {total_pages}",
                ]
            )

            text = "\n".join(lines)

        keyboard = leaderboard_keyboard(
            page,
            total_users,
        )

        # -------------------------------------------------
        # EDIT EXISTING MESSAGE
        # -------------------------------------------------

        if message_id is not None:
            try:
                bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return

            except Exception as error:
                if "message is not modified" in str(error).lower():
                    return

                logger.exception(
                    "Could not edit leaderboard message"
                )

        # -------------------------------------------------
        # SEND NEW MESSAGE IF EDIT FAILED
        # -------------------------------------------------

        bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception:
        logger.exception(
            "Failed to load Top 50 leaderboard"
        )

        try:
            bot.send_message(
                chat_id,
                (
                    "❌ Leaderboard open nahi ho paaya.\n"
                    "Please try again."
                ),
            )
        except Exception:
            logger.exception(
                "Could not send leaderboard error message"
            )


# =========================================================
# CHECK MEMBERSHIP FOR CALLBACKS
# =========================================================

def verify_callback_membership(call):
    if check_membership(call.from_user.id):
        complete_verification(call.from_user.id)
        return True

    bot.send_message(
        call.message.chat.id,
        (
            "⚠️ Please join both our group and channel "
            "to continue."
        ),
        reply_markup=join_keyboard(),
    )

    return False


# =========================================================
# COMMAND: /STATS
# =========================================================

@bot.message_handler(commands=["stats"])
def statistics_command(message):
    show_statistics(message)


# =========================================================
# BUTTON: STATISTICS
# =========================================================

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

        if not verify_callback_membership(call):
            return

        bot.edit_message_text(
            text=build_statistics_text(),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=statistics_keyboard(),
        )

    except Exception:
        logger.exception(
            "Statistics refresh callback failed"
        )


# =========================================================
# CALLBACK: OPEN TOP 50
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "top50_leaderboard"
)
def top50_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not verify_callback_membership(call):
            return

        show_top50(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            page=0,
        )

    except Exception:
        logger.exception(
            "Top 50 leaderboard callback failed"
        )


# =========================================================
# CALLBACK: NEXT / BACK PAGE
# =========================================================

@bot.callback_query_handler(
    func=lambda call: (
        call.data is not None
        and call.data.startswith("top50_page:")
    )
)
def top50_page_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not verify_callback_membership(call):
            return

        try:
            page = int(
                call.data.split(":", 1)[1]
            )
        except (ValueError, IndexError):
            page = 0

        show_top50(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            page=page,
        )

    except Exception:
        logger.exception(
            "Leaderboard page navigation failed"
        )


# =========================================================
# CALLBACK: BACK TO STATISTICS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "back_to_statistics"
)
def back_to_statistics_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not verify_callback_membership(call):
            return

        bot.edit_message_text(
            text=build_statistics_text(),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=statistics_keyboard(),
        )

    except Exception:
        logger.exception(
            "Back to statistics callback failed"
        )


# =========================================================
# CALLBACK: CHECK JOIN
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
                show_alert=True,
            )

        else:
            bot.answer_callback_query(
                call.id,
                "❌ Please join both the group and channel.",
                show_alert=True,
            )

    except Exception:
        logger.exception(
            "Check membership callback failed"
        )

        try:
            bot.answer_callback_query(
                call.id,
                "Verification failed. Please try again.",
                show_alert=True,
            )
        except Exception:
            pass
