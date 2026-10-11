from telebot import types

from bot import bot

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
    WELCOME_BONUS,
    REFERRAL_REWARD
)

from database import (
    register_user,
    get_user,
    get_user_stats,
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


def send_welcome(chat_id, first_name, bonus=0, balance=None):
    text = (
        f"👋 Welcome, <b>{first_name}</b>!\n\n"
        "🎉 Aapka verification complete ho gaya hai.\n\n"
    )

    if bonus > 0:
        text += (
            f"🎁 Welcome Bonus: <b>+{bonus} Coins</b>\n"
        )

    if balance is not None:
        text += (
            f"💰 Current Balance: <b>{balance} Coins</b>\n"
        )

    text += "\nNeeche se apna option select karo. ❤️🤍"

    bot.send_message(
        chat_id,
        text,
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


def send_referral_notifications(result):
    rewarded_referrals = result.get(
        "newly_rewarded_referrals",
        []
    )

    for referral in rewarded_referrals:
        referrer_id = referral["referrer_id"]
        referred_user_id = referral["referred_user_id"]

        referred_name = referral.get(
            "referred_user_name",
            "User"
        )

        referred_username = referral.get(
            "referred_user_username",
            ""
        )

        referrer_name = referral.get(
            "referrer_name",
            "User"
        )

        referrer_username = referral.get(
            "referrer_username",
            ""
        )

        reward = referral.get(
            "reward",
            REFERRAL_REWARD
        )

        referrer_balance = referral.get(
            "referrer_balance",
            0
        )

        referred_display = f"<b>{referred_name}</b>"

        if referred_username:
            referred_display += f" (@{referred_username})"

        referrer_display = f"<b>{referrer_name}</b>"

        if referrer_username:
            referrer_display += f" (@{referrer_username})"

        try:
            bot.send_message(
                referrer_id,
                "🎉 <b>Successful Referral!</b>\n\n"
                f"👤 {referred_display} ne aapka referral link use karke "
                "group aur channel verification complete kar liya.\n\n"
                f"🪙 Referral Reward: <b>+{reward} Coins</b>\n"
                f"💰 Current Balance: <b>{referrer_balance} Coins</b>\n\n"
                "Thank you for referring! ❤️🤍",
                parse_mode="HTML"
            )
        except Exception:
            pass

        try:
            user_stats = get_user_stats(referred_user_id)
            user_balance = user_stats["coins_balance"]

            bot.send_message(
                referred_user_id,
                "🎉 <b>Referral Verified Successfully!</b>\n\n"
                f"👑 Referred By: {referrer_display}\n"
                f"🎁 Welcome Bonus: <b>+{WELCOME_BONUS} Coins</b>\n"
                f"💰 Current Balance: <b>{user_balance} Coins</b>\n\n"
                "Aapka referral successfully verify ho gaya hai. ❤️🤍",
                parse_mode="HTML"
            )
        except Exception:
            pass


def finish_verification(chat_id, user_id, first_name):
    result = complete_verification(user_id)

    if not result["success"]:
        bot.send_message(
            chat_id,
            "❌ Verification complete nahi ho paya.\n"
            "Please dobara /start try karo."
        )
        return

    send_welcome(
        chat_id,
        first_name,
        result.get("welcome_bonus", 0),
        result.get("coins_balance", 0)
    )

    send_referral_notifications(result)


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

    if existing_user and existing_user.get("is_verified"):
        bot.send_message(
            message.chat.id,
            "❤️🤍 <b>Welcome Back!</b>\n\n"
            "Neeche se apna option select karo.",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        return

    finish_verification(
        message.chat.id,
        user_id,
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

    if user.get("is_verified"):
        bot.answer_callback_query(
            call.id,
            "Aapka verification pehle se complete hai!"
        )

        try:
            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )
        except Exception:
            pass

        bot.send_message(
            call.message.chat.id,
            "❤️🤍 <b>Welcome Back!</b>\n\n"
            "Aapka account pehle se verified hai.",
            reply_markup=main_menu(),
            parse_mode="HTML"
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

    finish_verification(
        call.message.chat.id,
        user_id,
        first_name
    )
