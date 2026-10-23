from html import escape

from telebot import types

from bot import bot

from config import (
    GROUP_ID,
    GROUP_INVITE_LINK,
    CHANNEL_ID,
    CHANNEL_INVITE_LINK,
    WELCOME_BONUS,
    REFERRAL_REWARD,
)

from database import (
    register_user,
    get_user,
    get_user_stats,
    complete_verification,
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

        allowed_statuses = (
            "member",
            "administrator",
            "creator",
        )

        return (
            group_member.status in allowed_statuses
            and channel_member.status in allowed_statuses
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
            "✅ Check Join",
            callback_data="check_join"
        )
    )

    return keyboard


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row(
        types.KeyboardButton("👤 Profile")
    )

    keyboard.row(
        types.KeyboardButton("📊 Statistics"),
        types.KeyboardButton("👥 Refer & Earn")
    )

    keyboard.row(
        types.KeyboardButton("🔓 Open Links")
    )

    keyboard.row(
        types.KeyboardButton("🎁 Daily Bonus"),
        types.KeyboardButton("🎁 Redeem Code")
    )

    return keyboard


# =========================================================
# JOIN MESSAGE
# =========================================================

def send_join_message(chat_id):
    bot.send_message(
        chat_id,
        (
           "👋 <b>Welcome! 🤫</b>\n\n"
"To use this bot, please join both our group and channel.\n\n"
"After joining, tap <b>Check Join to continue. ✅</b>"
        ),
        parse_mode="HTML",
        reply_markup=join_keyboard()
    )


# =========================================================
# GET REFERRER DISPLAY NAME
# USERNAME FIRST, NAME AS FALLBACK
# =========================================================

def get_referrer_name(result):
    username = result.get("referrer_username")

    if username and str(username).strip():
        return f"@{str(username).strip().lstrip('@')}"

    name = result.get("referrer_name")

    if name and str(name).strip():
        return str(name).strip()

    return "A fellow member"


# =========================================================
# NOTIFY REFERRED USER
# =========================================================

def notify_referred_user(user_id, result):
    """
    Sends a notification to the referred user
    containing the referrer's information.

    The notification is sent when the welcome
    bonus is credited for the first time.
    """

    welcome_bonus = result.get("welcome_bonus", 0)

    if welcome_bonus <= 0:
        return

    referrer_id = result.get("referrer_id")

    if not referrer_id or referrer_id == user_id:
        return

    referrer_display = escape(
        get_referrer_name(result)
    )

    user = get_user(user_id)

    balance = 0

    if isinstance(user, dict):
        balance = user.get("coins_balance", 0)

    message = (
        "🎉 <b>Welcome to Refer &amp; Earn Bot!</b>\n\n"
        "👥 <b>You joined using a referral link!</b>\n\n"
        f"🤝 <b>Referred By:</b> {referrer_display}\n"
        f"🎁 <b>Welcome Bonus:</b> +{welcome_bonus} Coins\n"
        f"🪙 <b>Your Balance:</b> {balance} Coins\n\n"
        "💓 Welcome aboard!\n"
        "🤍 Refer your friends and earn more coins."
    )

    try:
        bot.send_message(
            user_id,
            message,
            parse_mode="HTML"
        )

    except Exception as error:
        print(
            f"Referred user notification error: {error}"
        )


# =========================================================
# NOTIFY REFERRER ABOUT REWARD
# =========================================================

def notify_referral_rewards(result):
    for item in result.get(
        "newly_rewarded_referrals",
        []
    ):
        referrer_id = item.get("referrer_id")

        referred_username = item.get(
            "referred_user_username"
        )

        referred_name = item.get(
            "referred_user_name"
        )

        # Referred user ka username first preference.
        if referred_username and str(
            referred_username
        ).strip():
            referral_display = (
                f"@{str(referred_username).strip().lstrip('@')}"
            )
        elif referred_name:
            referral_display = str(referred_name)
        else:
            referral_display = "User"

        reward = item.get(
            "reward",
            REFERRAL_REWARD
        )

        balance = item.get(
            "referrer_balance",
            0
        )

        if not referrer_id:
            continue

        try:
            bot.send_message(
                referrer_id,
                (
                    "🎉 <b>Referral Reward Received!</b>\n\n"
                    f"👤 <b>Referral:</b> "
                    f"{escape(referral_display)}\n"
                    f"🪙 <b>Reward:</b> +{reward} Coins\n"
                    f"💰 <b>Current Balance:</b> "
                    f"{balance} Coins"
                ),
                parse_mode="HTML"
            )

        except Exception as error:
            print(
                f"Referral notification error: {error}"
            )


# =========================================================
# PROCESS VERIFICATION
# =========================================================

def process_verification(user_id):
    result = complete_verification(user_id)

    if not result.get("success"):
        return result

    # Referral se join karne wale user ko notification.
    notify_referred_user(
        user_id,
        result
    )

    # Referrer ko reward credit hone par notification.
    notify_referral_rewards(result)

    return result


# =========================================================
# WELCOME MESSAGE
# =========================================================

def send_welcome(chat_id, first_name):
    safe_name = escape(first_name or "User")

    bot.send_message(
        chat_id,
        (
           f"🎉 <b>Welcome, {safe_name}!</b>\n\n"
f"🎁 Welcome Bonus: <b>+{WELCOME_BONUS} coins</b>\n"
f"👥 Your Referral Reward: <b>{REFERRAL_REWARD} coins</b>\n\n"
"🪙 To check your balance, click on "
"<b>👤 Profile</b>.\n\n"
"Select an option from the menu below. 👇"
        ),
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================================================
# PROFILE
# =========================================================

def show_profile(chat_id, user_id):
    user = get_user(user_id)

    if not user:
        bot.send_message(
            chat_id,
            "❌ Profile not found. Please use /start to get started."
        )
        return

    if isinstance(user, dict):
        first_name = user.get("first_name") or "User"
        username = user.get("username") or ""
        balance = user.get("coins_balance", 0)
        total_earned = user.get(
            "total_coins_earned",
            0
        )

    else:
        first_name = (
            user[1] if len(user) > 1 else "User"
        )
        username = (
            user[2] if len(user) > 2 else ""
        )
        balance = (
            user[3] if len(user) > 3 else 0
        )
        total_earned = (
            user[4] if len(user) > 4 else 0
        )

    stats = get_user_stats(user_id)

    if isinstance(stats, dict):
        successful_referrals = stats.get(
            "referral_count",
            0
        )
    elif isinstance(stats, (tuple, list)):
        successful_referrals = (
            stats[0] if stats else 0
        )
    else:
        successful_referrals = 0

    display_username = (
        f"@{escape(str(username).lstrip('@'))}"
        if username
        else "No Username"
    )

    text = (
        "👤 <b>MY PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 <b>Name:</b> {escape(str(first_name))}\n"
        f"🔗 <b>Username:</b> {display_username}\n"
        f"🆔 <b>Chat ID:</b> <code>{user_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 <b>Current Balance:</b> {balance} Coins\n"
        f"🎁 <b>Total Coins Earned:</b> "
        f"{total_earned} Coins\n"
        f"👥 <b>Successful Referrals:</b> "
        f"{successful_referrals}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💎 Keep Referring &amp; Earn More!"
    )

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================================================
# PROFILE BUTTON
# =========================================================

@bot.message_handler(
    func=lambda message: message.text == "👤 Profile"
)
def profile_button(message):
    show_profile(
        chat_id=message.chat.id,
        user_id=message.from_user.id
    )


# =========================================================
# FINISH VERIFICATION
# =========================================================

def finish_verification(message):
    user_id = message.from_user.id

    result = process_verification(user_id)

    if not result.get("success"):
        bot.send_message(
            message.chat.id,
            "❌ Verification failed. Please try again."
        )
        return

    welcome_bonus = result.get(
        "welcome_bonus",
        0
    )

    if welcome_bonus > 0:
        user = get_user(user_id)

        balance = (
            user.get("coins_balance", 0)
            if isinstance(user, dict)
            else 0
        )

        bot.send_message(
            message.chat.id,
            (
                "🎉 <b>Coins Credited Successfully!</b>\n\n"
                f"🎁 Welcome Bonus: <b>+{welcome_bonus} Coins</b>\n"
                f"🪙 <b>Current Balance:</b> "
                f"{balance} Coins"
            ),
            parse_mode="HTML"
        )

    bot.send_message(
        message.chat.id,
        (
           "✅ Verification successful!\n\n"
"Please select an option from the menu below. 👇"
        ),
        reply_markup=main_menu()
    )


# =========================================================
# START COMMAND
# =========================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id

    first_name = (
        message.from_user.first_name or "User"
    )

    username = (
        message.from_user.username or ""
    )

    referred_by = None

    parts = (message.text or "").split(
        maxsplit=1
    )

    if len(parts) > 1:
        referral_parameter = parts[1].strip()

        if referral_parameter.isdigit():
            potential_referrer = int(
                referral_parameter
            )

            if potential_referrer != user_id:
                referred_by = potential_referrer

    is_new_user = register_user(
        user_id=user_id,
        first_name=first_name,
        username=username,
        referred_by=referred_by
    )

    user = get_user(user_id)

    if not user:
        bot.send_message(
            message.chat.id,
            "❌ User registration failed. Please try again."
        )
        return

    if not check_membership(user_id):
        send_join_message(
            message.chat.id
        )
        return

    result = process_verification(user_id)

    if not result.get("success"):
        bot.send_message(
            message.chat.id,
            (
                "❌ Verification failed. "
"Please try /start again."
            )
        )
        return

    if is_new_user:
        send_welcome(
            message.chat.id,
            first_name
        )

    else:
        bot.send_message(
            message.chat.id,
            (
              "👋 <b>Welcome back!</b>\n\n"
"🪙 To check your balance, tap "
"<b>👤 Profile</b>.\n\n"
"Please select an option from the menu below. 👇"
            ),
            parse_mode="HTML",
            reply_markup=main_menu()
        )


# =========================================================
# CHECK JOIN CALLBACK
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "check_join"
)
def check_join_callback(call):
    user_id = call.from_user.id

    if check_membership(user_id):
        result = process_verification(user_id)

        if not result.get("success"):
            bot.answer_callback_query(
                call.id,
                "❌ Verification failed. Try again.",
                show_alert=True
            )
            return

        bot.answer_callback_query(
            call.id,
            "✅ Membership verified!"
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
            (
                "🎉 Verification successful!\n\n"
"Please select an option from the menu below. 👇"
            ),
            reply_markup=main_menu()
        )

    else:
        bot.answer_callback_query(
            call.id,
            "❌ Please join both the group and the channel.",
            show_alert=True
        )
