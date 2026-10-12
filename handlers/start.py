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
            "creator"
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
        types.KeyboardButton("📊 Statistics"),
        types.KeyboardButton("👥 Refer & Earn")
    )

    keyboard.row(
        types.KeyboardButton("🔓 Open Links")
    )

    keyboard.row(
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
            "👋 <b>Welcome!</b>\n\n"
            "Bot use karne ke liye hamara group aur channel "
            "dono join karo.\n\n"
            "Join karne ke baad <b>✅ Check Join</b> dabao."
        ),
        parse_mode="HTML",
        reply_markup=join_keyboard()
    )


# =========================================================
# WELCOME MESSAGE
# =========================================================

def send_welcome(chat_id, first_name):
    name = types.utils.markdown.escape(first_name or "User")

    text = (
        f"🎉 Welcome, {name}!\n\n"
        f"🎁 Welcome Bonus: {WELCOME_BONUS} coins\n"
        f"👥 Referral Reward: {REFERRAL_REWARD} coins\n\n"
        "Neeche se option select karo. 👇"
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=main_menu()
    )


# =========================================================
# REFERRAL NOTIFICATIONS
# =========================================================

def notify_referral_rewards(result):
    for item in result.get("newly_rewarded_referrals", []):
        referrer_id = item["referrer_id"]
        referred_name = item.get("referred_user_name") or "User"
        reward = item.get("reward", REFERRAL_REWARD)
        balance = item.get("referrer_balance", 0)

        try:
            bot.send_message(
                referrer_id,
                (
                    "🎉 <b>Referral Reward Received!</b>\n\n"
                    f"👤 Referral: {referred_name}\n"
                    f"🪙 Reward: +{reward} coins\n"
                    f"💰 Current Balance: {balance} coins"
                ),
                parse_mode="HTML"
            )

        except Exception as error:
            print(f"Referral notification error: {error}")


# =========================================================
# FINISH VERIFICATION
# =========================================================

def finish_verification(message):
    user_id = message.from_user.id

    result = complete_verification(user_id)

    if not result.get("success"):
        bot.send_message(
            message.chat.id,
            "❌ Verification nahi ho paayi. Dobara try karo."
        )
        return

    notify_referral_rewards(result)

    if result.get("welcome_bonus", 0) > 0:
        bot.send_message(
            message.chat.id,
            (
                f"🎁 Welcome bonus: "
                f"+{result['welcome_bonus']} coins!"
            )
        )

    bot.send_message(
        message.chat.id,
        "✅ Verification successful!\n\nNeeche se option select karo. 👇",
        reply_markup=main_menu()
    )


# =========================================================
# START COMMAND
# =========================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    username = message.from_user.username or ""

    referred_by = None

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) > 1:
        referral_parameter = parts[1].strip()

        if referral_parameter.isdigit():
            potential_referrer = int(referral_parameter)

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
        send_join_message(message.chat.id)
        return

    result = complete_verification(user_id)

    if result.get("success"):
        notify_referral_rewards(result)

    if is_new_user:
        send_welcome(
            message.chat.id,
            first_name
        )
    else:
        bot.send_message(
            message.chat.id,
            "👋 Welcome back!\n\nNeeche se option select karo. 👇",
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
        complete_verification(user_id)

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
            "🎉 Verification successful!\n\nNeeche se option select karo. 👇",
            reply_markup=main_menu()
        )

    else:
        bot.answer_callback_query(
            call.id,
            "❌ Group aur channel dono join karo.",
            show_alert=True
        )
