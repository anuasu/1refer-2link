from telebot import types

from bot import bot

from database import (
    get_user,
    get_user_stats,
    complete_verification
)

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
    REFERRAL_REWARD
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

        return (
            group_member.status in valid_statuses
            and channel_member.status in valid_statuses
        )

    except Exception:
        return False


def referral_join_keyboard():
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


def show_referral_info(message):
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
            "🔐 Referral system use karne ke liye "
            "group aur channel dono join karo.",
            reply_markup=referral_join_keyboard()
        )
        return

    complete_verification(user_id)

    stats = get_user_stats(user_id)

    bot_username = bot.get_me().username

    referral_link = (
        f"https://t.me/{bot_username}?start={user_id}"
    )

    text = (
        "👥 <b>REFER &amp; EARN</b>\n\n"
        "Apna referral link friends ke saath share karo!\n\n"
        f"🎁 Har successful referral par "
        f"<b>+{REFERRAL_REWARD} Coins</b> milenge.\n\n"
        "🔗 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👤 Successful Referrals: "
        f"<b>{stats['referral_count']}</b>\n"
        f"🪙 Total Coins Earned: "
        f"<b>{stats['total_coins_earned']}</b>\n"
        f"💰 Current Balance: "
        f"<b>{stats['coins_balance']}</b>"
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📤 Share Referral Link",
            url=(
                "https://t.me/share/url"
                f"?url={referral_link}"
            )
        )
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.message_handler(commands=["referral"])
def referral_command(message):
    show_referral_info(message)


@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() == "👥 Refer & Earn"
    )
)
def referral_button(message):
    show_referral_info(message)
