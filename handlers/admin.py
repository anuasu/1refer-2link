import re
import secrets
import string
import logging
from datetime import datetime, timedelta

from telebot import types

from bot import bot

from config import (
    ADMIN_IDS,
    CHANNEL_ID,
    TIMEZONE,
)

from database import (
    add_links,
    get_active_links,
    get_links_count,
    delete_link,
    create_redeem_code,
    get_redeem_code,
    get_redeem_codes,
    deactivate_redeem_code,
    get_redeem_settings,
    update_redeem_settings,
    generate_redeem_expiry,
)

logger = logging.getLogger(__name__)

admin_sessions = {}


# ==========================================
# ADMIN HELPERS
# ==========================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔗 Add Links",
            callback_data="admin_add_links"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🎁 Redeem Code Management",
            callback_data="admin_redeem"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Broadcast",
            callback_data="admin_broadcast"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "💾 Backup & Recovery",
            callback_data="admin_backup"
        )
    )

    return keyboard


def send_admin_panel(chat_id):
    total_links = get_links_count()

    text = (
        "👑 <b>ADMIN PANEL</b>\n\n"
        "Welcome to the admin control panel.\n\n"
        f"🔗 Active Links: <b>{total_links}</b>\n\n"
        "Neeche se option select karo."
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )


def cancel_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data="admin_cancel_action"
        )
    )

    return keyboard


# ==========================================
# ADMIN COMMAND
# ==========================================

@bot.message_handler(commands=["admin"])
def admin_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "⛔ Only admin can access this panel."
        )
        return

    send_admin_panel(message.chat.id)


# ==========================================
# ADD LINKS
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data == "admin_add_links"
)
def add_links_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    admin_sessions[call.from_user.id] = "waiting_for_links"

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🔗 <b>ADD LINKS</b>\n\n"
        "Ek message mein ek ya multiple links bhejo.\n\n"
        "Example:\n"
        "https://example.com/link1\n"
        "https://example.com/link2\n"
        "https://t.me/example\n\n"
        "Links spaces ya new lines se separate kar sakte ho.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


def extract_links(text):
    pattern = r"https?://[^\s<>]+|t\.me/[^\s<>]+"
    matches = re.findall(pattern, text)

    links = []

    for link in matches:
        link = link.strip().rstrip(".,;!?)\"]}")

        if link.startswith("t.me/"):
            link = "https://" + link

        if link not in links:
            links.append(link)

    return links


@bot.message_handler(
    func=lambda message: (
        message.from_user is not None
        and admin_sessions.get(message.from_user.id)
        == "waiting_for_links"
    ),
    content_types=["text"]
)
def receive_links(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        admin_sessions.pop(user_id, None)
        return

    if message.text.strip().lower() in ("/cancel", "cancel"):
        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "❌ Add Links cancelled.",
            reply_markup=admin_keyboard()
        )
        return

    links = extract_links(message.text)

    if not links:
        bot.send_message(
            message.chat.id,
            "❌ Koi valid URL nahi mila.\n\n"
            "HTTPS URL ya t.me link bhejo."
        )
        return

    try:
        added_ids = add_links(links, user_id)
    except Exception:
        logger.exception("Failed to add links")
        bot.send_message(
            message.chat.id,
            "❌ Links save nahi ho paaye. Dobara try karo."
        )
        return

    admin_sessions.pop(user_id, None)

    if not added_ids:
        bot.send_message(
            message.chat.id,
            "❌ Links save nahi ho paaye.",
            reply_markup=admin_keyboard()
        )
        return

    bot.send_message(
        message.chat.id,
        "✅ <b>LINKS ADDED SUCCESSFULLY</b>\n\n"
        f"🔗 Links added: <b>{len(added_ids)}</b>\n"
        f"📊 Total active links: <b>{get_links_count()}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# REDEEM ADMIN MENU
# ==========================================

def redeem_admin_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "➕ Create Manual Code",
            callback_data="redeem_create_manual"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🎲 Generate Random Code",
            callback_data="redeem_create_random"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📋 View Codes",
            callback_data="redeem_view_codes"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🤖 Auto Code Settings",
            callback_data="redeem_auto_settings"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🔙 Admin Panel",
            callback_data="redeem_back_admin"
        )
    )

    return keyboard


def show_redeem_admin(chat_id):
    try:
        settings = get_redeem_settings() or {}
        auto_enabled = settings.get("auto_enabled", 0)
        post_time = settings.get("post_time", "11:00")
        reward = settings.get("reward_coins", 10)
        max_users = settings.get("max_users", 100)
        expiry_hours = settings.get("expiry_hours", 24)

        text = (
            "🎁 <b>REDEEM CODE MANAGEMENT</b>\n\n"
            f"🤖 Automatic Codes: "
            f"<b>{'ON' if auto_enabled else 'OFF'}</b>\n"
            f"🕒 Daily Post Time: <b>{post_time}</b>\n"
            f"🪙 Default Reward: <b>{reward} coins</b>\n"
            f"👥 Maximum Users: <b>{max_users}</b>\n"
            f"⏳ Expiry: <b>{expiry_hours} hours</b>\n\n"
            "Manual codes can be created independently."
        )

    except Exception:
        logger.exception("Unable to load redeem settings")
        text = (
            "🎁 <b>REDEEM CODE MANAGEMENT</b>\n\n"
            "Settings load nahi ho paayi. Database check karo."
        )

    bot.send_message(
        chat_id,
        text,
        reply_markup=redeem_admin_keyboard(),
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_redeem"
)
def redeem_admin_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)
    show_redeem_admin(call.message.chat.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_back_admin"
)
def redeem_back_admin_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)
    send_admin_panel(call.message.chat.id)


# ==========================================
# CREATE MANUAL / RANDOM CODE
# ==========================================

def generate_random_code(length=12):
    alphabet = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


def ask_code_reward(chat_id, user_id, code):
    admin_sessions[user_id] = {
        "action": "redeem_reward",
        "code": code
    }

    bot.send_message(
        chat_id,
        f"🎁 Code: <code>{code}</code>\n\n"
        "Kitne coins ka reward dena hai?\n\n"
        "Example: <code>100</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data in (
        "redeem_create_manual",
        "redeem_create_random"
    )
)
def redeem_create_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)

    if call.data == "redeem_create_random":
        code = generate_random_code()
        ask_code_reward(
            call.message.chat.id,
            call.from_user.id,
            code
        )
        return

    admin_sessions[call.from_user.id] = {
        "action": "redeem_manual_code"
    }

    bot.send_message(
        call.message.chat.id,
        "✍️ Apna custom redeem code bhejo.\n\n"
        "Example: <code>WELCOME100</code>\n"
        "Sirf letters, numbers, hyphen aur underscore allowed hain.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# RECEIVE CODE CREATION DETAILS
# ==========================================

def ask_code_max_users(message, user_id, code, reward):
    admin_sessions[user_id] = {
        "action": "redeem_max_users",
        "code": code,
        "reward": reward
    }

    bot.send_message(
        message.chat.id,
        "👥 Maximum kitne users code redeem kar sakenge?\n\n"
        "Example: <code>100</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


def ask_code_expiry(message, user_id, code, reward, max_users):
    admin_sessions[user_id] = {
        "action": "redeem_expiry",
        "code": code,
        "reward": reward,
        "max_users": max_users
    }

    bot.send_message(
        message.chat.id,
        "⏳ Code kitne hours tak valid rahe?\n\n"
        "Example: <code>24</code>\n"
        "Expiry nahi chahiye toh <code>0</code> bhejo.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


def finish_create_code(message, user_id, code, reward, max_users, expiry_hours):
    expires_at = None

    if expiry_hours > 0:
        expires_at = generate_redeem_expiry(expiry_hours)

    try:
        created = create_redeem_code(
            code=code,
            reward_coins=reward,
            max_users=max_users,
            expires_at=expires_at,
            created_by=user_id,
            is_auto=False,
            channel_id=CHANNEL_ID
        )
    except Exception:
        logger.exception("Redeem code creation failed")
        bot.send_message(
            message.chat.id,
            "❌ Code create nahi hua. Ho sakta hai ye code pehle se exist karta ho."
        )
        return

    if not created:
        bot.send_message(
            message.chat.id,
            "❌ Code create nahi hua. Code pehle se exist kar sakta hai."
        )
        return

    admin_sessions.pop(user_id, None)

    text = (
        "✅ <b>REDEEM CODE CREATED</b>\n\n"
        f"🎟 Code: <code>{code}</code>\n"
        f"🪙 Reward: <b>{reward} coins</b>\n"
        f"👥 Maximum users: <b>{max_users}</b>\n"
        f"⏳ Expiry: <b>{expiry_hours if expiry_hours else 'No expiry'}"
        f"{' hours' if expiry_hours else ''}</b>\n\n"
        "Code users ke redeem menu mein use kiya ja sakta hai."
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 Post Code to Channel",
            callback_data=f"redeem_post_{code}"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🎁 Redeem Management",
            callback_data="admin_redeem"
        )
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==========================================
# CODE INPUT HANDLER
# ==========================================

@bot.message_handler(
    func=lambda message: (
        message.from_user is not None
        and isinstance(admin_sessions.get(message.from_user.id), dict)
        and admin_sessions[message.from_user.id].get("action")
        in (
            "redeem_manual_code",
            "redeem_reward",
            "redeem_max_users",
            "redeem_expiry",
            "redeem_auto_channel",
            "redeem_auto_time",
            "redeem_auto_reward",
            "redeem_auto_max",
            "redeem_auto_expiry"
        )
    ),
    content_types=["text"]
)
def receive_redeem_admin_input(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        admin_sessions.pop(user_id, None)
        return

    value = message.text.strip()
    session = admin_sessions.get(user_id, {})
    action = session.get("action")

    if value.lower() in ("/cancel", "cancel"):
        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "❌ Action cancelled.",
            reply_markup=admin_keyboard()
        )
        return

    if action == "redeem_manual_code":
        code = value.upper()

        if not re.fullmatch(r"[A-Z0-9_-]{3,40}", code):
            bot.send_message(
                message.chat.id,
                "❌ Invalid code. 3–40 characters use karo; "
                "letters, numbers, _ aur - allowed hain."
            )
            return

        ask_code_reward(message.chat.id, user_id, code)
        return

    if action == "redeem_reward":
        if not value.isdigit() or int(value) <= 0:
            bot.send_message(
                message.chat.id,
                "❌ Reward positive whole number hona chahiye."
            )
            return

        reward = int(value)

        if reward > 1_000_000_000:
            bot.send_message(message.chat.id, "❌ Reward bahut zyada hai.")
            return

        ask_code_max_users(
            message,
            user_id,
            session["code"],
            reward
        )
        return

    if action == "redeem_max_users":
        if not value.isdigit() or int(value) <= 0:
            bot.send_message(
                message.chat.id,
                "❌ Maximum users positive whole number hona chahiye."
            )
            return

        max_users = int(value)

        if max_users > 1_000_000:
            bot.send_message(message.chat.id, "❌ Maximum users limit bahut zyada hai.")
            return

        ask_code_expiry(
            message,
            user_id,
            session["code"],
            session["reward"],
            max_users
        )
        return

    if action == "redeem_expiry":
        if not value.isdigit():
            bot.send_message(
                message.chat.id,
                "❌ Hours mein number bhejo, example: 24. No expiry ke liye 0."
            )
            return

        expiry_hours = int(value)

        if expiry_hours > 87600:
            bot.send_message(message.chat.id, "❌ Expiry maximum 10 years tak rakho.")
            return

        finish_create_code(
            message,
            user_id,
            session["code"],
            session["reward"],
            session["max_users"],
            expiry_hours
        )
        return

    if action == "redeem_auto_channel":
        try:
            channel_id = int(value)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Channel ID number hona chahiye.\n"
                "Example: <code>-1001234567890</code>",
                parse_mode="HTML"
            )
            return

        try:
            update_redeem_settings(channel_id=channel_id)
        except Exception:
            logger.exception("Could not update channel ID")
            bot.send_message(message.chat.id, "❌ Channel ID save nahi hua.")
            return

        admin_sessions[user_id] = {"action": "redeem_auto_time"}

        bot.send_message(
            message.chat.id,
            "🕒 Daily post time bhejo (24-hour format).\n"
            "Example: <code>11:00</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    if action == "redeem_auto_time":
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            bot.send_message(
                message.chat.id,
                "❌ Time HH:MM format mein bhejo, example: 11:00."
            )
            return

        try:
            update_redeem_settings(post_time=value)
        except Exception:
            logger.exception("Could not update auto post time")
            bot.send_message(message.chat.id, "❌ Time save nahi hua.")
            return

        admin_sessions[user_id] = {"action": "redeem_auto_reward"}

        bot.send_message(
            message.chat.id,
            "🪙 Daily code ka reward coins mein bhejo.\n"
            "Example: <code>100</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    if action == "redeem_auto_reward":
        if not value.isdigit() or int(value) <= 0:
            bot.send_message(message.chat.id, "❌ Positive reward number bhejo.")
            return

        try:
            update_redeem_settings(reward_coins=int(value))
        except Exception:
            logger.exception("Could not update auto reward")
            bot.send_message(message.chat.id, "❌ Reward save nahi hua.")
            return

        admin_sessions[user_id] = {"action": "redeem_auto_max"}

        bot.send_message(
            message.chat.id,
            "👥 Daily code ka maximum users number bhejo.\n"
            "Example: <code>100</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    if action == "redeem_auto_max":
        if not value.isdigit() or int(value) <= 0:
            bot.send_message(message.chat.id, "❌ Positive user limit bhejo.")
            return

        try:
            update_redeem_settings(max_users=int(value))
        except Exception:
            logger.exception("Could not update auto max users")
            bot.send_message(message.chat.id, "❌ User limit save nahi hui.")
            return

        admin_sessions[user_id] = {"action": "redeem_auto_expiry"}

        bot.send_message(
            message.chat.id,
            "⏳ Daily code ki expiry hours mein bhejo.\n"
            "Example: <code>24</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    if action == "redeem_auto_expiry":
        if not value.isdigit() or int(value) < 1:
            bot.send_message(
                message.chat.id,
                "❌ Expiry kam se kam 1 hour honi chahiye."
            )
            return

        if int(value) > 87600:
            bot.send_message(message.chat.id, "❌ Expiry maximum 10 years tak rakho.")
            return

        try:
            update_redeem_settings(
                expiry_hours=int(value),
                auto_enabled=1
            )
        except Exception:
            logger.exception("Could not save auto settings")
            bot.send_message(message.chat.id, "❌ Auto settings save nahi hui.")
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ <b>Automatic code settings saved!</b>\n\n"
            "Auto mode ON hai. Daily scheduler ko `main.py` mein "
            "configure karna abhi baaki hai.",
            reply_markup=redeem_admin_keyboard(),
            parse_mode="HTML"
        )


# ==========================================
# VIEW CODES
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_view_codes"
)
def redeem_view_codes_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    try:
        codes = get_redeem_codes(limit=15)
    except Exception:
        logger.exception("Could not list redeem codes")
        bot.send_message(call.message.chat.id, "❌ Codes load nahi ho paaye.")
        return

    if not codes:
        bot.send_message(
            call.message.chat.id,
            "📭 Abhi koi redeem code nahi bana hai.",
            reply_markup=redeem_admin_keyboard()
        )
        return

    for item in codes:
        code = str(item.get("code", ""))
        reward = item.get("reward_coins", 0)
        max_users = item.get("max_users", 0)
        redeemed_count = item.get("redeemed_count", 0)
        active = item.get("is_active", 0)
        expires = item.get("expires_at") or "No expiry"

        text = (
            f"🎟️ Code: <code>{code}</code>\n"
            f"🪙 Reward: <b>{reward}</b> coins\n"
            f"👥 Redeemed: <b>{redeemed_count}/{max_users}</b>\n"
            f"📌 Status: <b>{'Active' if active else 'Inactive'}</b>\n"
            f"⏳ Expiry: <code>{expires}</code>"
        )

        keyboard = types.InlineKeyboardMarkup()

        if active:
            keyboard.add(
                types.InlineKeyboardButton(
                    "🚫 Deactivate Code",
                    callback_data=f"redeem_deactivate_{code}"
                )
            )

        bot.send_message(
            call.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


# ==========================================
# DEACTIVATE CODE
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("redeem_deactivate_")
)
def redeem_deactivate_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    code = call.data[len("redeem_deactivate_"):]

    try:
        result = deactivate_redeem_code(code)
    except Exception:
        logger.exception("Could not deactivate redeem code")
        bot.answer_callback_query(
            call.id,
            "Database error.",
            show_alert=True
        )
        return

    if result:
        bot.answer_callback_query(call.id, "Code deactivated.")
        bot.send_message(
            call.message.chat.id,
            f"🚫 Code <code>{code}</code> deactivated.",
            parse_mode="HTML"
        )
    else:
        bot.answer_callback_query(
            call.id,
            "Code nahi mila ya deactivate nahi hua.",
            show_alert=True
        )


# ==========================================
# POST CODE TO CHANNEL
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("redeem_post_")
)
def redeem_post_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    code = call.data[len("redeem_post_"):]

    try:
        item = get_redeem_code(code)
    except Exception:
        logger.exception("Could not retrieve code for posting")
        item = None

    if not item:
        bot.answer_callback_query(
            call.id,
            "Code nahi mila.",
            show_alert=True
        )
        return

    settings = get_redeem_settings() or {}
    channel_id = settings.get("channel_id") or CHANNEL_ID

    try:
        bot.get_chat_member(channel_id, bot.get_me().id)

        post_text = (
            "🎁 <b>REDEEM CODE AVAILABLE!</b>\n\n"
            f"🎟 Code: <code>{code}</code>\n"
            f"🪙 Reward: <b>{item.get('reward_coins', 0)} coins</b>\n"
            f"👥 Maximum users: <b>{item.get('max_users', 0)}</b>\n\n"
            "Bot open karo, 🎁 Redeem Code select karo aur code enter karo.\n"
            "Hurry! Limited redemptions available."
        )

        sent = bot.send_message(
            channel_id,
            post_text,
            parse_mode="HTML"
        )

        bot.answer_callback_query(
            call.id,
            "Code channel par post ho gaya!"
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ Code posted to channel.\nMessage ID: {sent.message_id}"
        )

    except Exception:
        logger.exception("Could not post redeem code to channel")
        bot.answer_callback_query(
            call.id,
            "Posting failed. Bot ko channel admin banao aur permissions check karo.",
            show_alert=True
        )


# ==========================================
# AUTOMATIC CODE SETTINGS
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_settings"
)
def redeem_auto_settings_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    settings = get_redeem_settings() or {}
    enabled = bool(settings.get("auto_enabled", 0))

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🟢 Turn Auto ON" if not enabled else "🔴 Turn Auto OFF",
            callback_data="redeem_auto_toggle"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "⚙️ Configure Daily Settings",
            callback_data="redeem_auto_configure"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="admin_redeem"
        )
    )

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🤖 <b>AUTOMATIC REDEEM CODES</b>\n\n"
        f"Status: <b>{'ON' if enabled else 'OFF'}</b>\n"
        f"Post time: <b>{settings.get('post_time', '11:00')}</b>\n"
        f"Channel ID: <code>{settings.get('channel_id') or CHANNEL_ID}</code>\n\n"
        "Auto ON/OFF sirf scheduler mode control karta hai. "
        "Manual codes alag se kaam karenge.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_toggle"
)
def redeem_auto_toggle_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    settings = get_redeem_settings() or {}
    new_value = 0 if settings.get("auto_enabled", 0) else 1

    try:
        update_redeem_settings(auto_enabled=new_value)
    except Exception:
        logger.exception("Could not toggle auto mode")
        bot.answer_callback_query(
            call.id,
            "Settings update failed.",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Auto mode ON" if new_value else "Auto mode OFF"
    )

    redeem_auto_settings_callback(
        type(
            "CallProxy",
            (),
            {
                "from_user": call.from_user,
                "data": "redeem_auto_settings",
                "id": call.id,
                "message": call.message
            }
        )()
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_configure"
)
def redeem_auto_configure_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    admin_sessions[call.from_user.id] = {
        "action": "redeem_auto_channel"
    }

    bot.send_message(
        call.message.chat.id,
        "📢 Automatic codes kis channel mein post karne hain?\n\n"
        "Channel ID bhejo.\n"
        "Example: <code>-1001234567890</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# CANCEL CALLBACK
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data == "admin_cancel_action"
)
def cancel_admin_action(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    admin_sessions.pop(call.from_user.id, None)

    bot.answer_callback_query(
        call.id,
        "Action cancelled."
    )

    bot.send_message(
        call.message.chat.id,
        "Admin action cancelled.",
        reply_markup=admin_keyboard()
    )


# ==========================================
# MANAGE LINKS
# ==========================================

@bot.message_handler(commands=["manage_links"])
def manage_links_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "⛔ Only admin can manage links."
        )
        return

    links = get_active_links()

    if not links:
        bot.reply_to(
            message,
            "📭 Abhi koi active link nahi hai."
        )
        return

    text = "🔗 <b>ACTIVE LINKS</b>\n\n"
    keyboard = types.InlineKeyboardMarkup()

    for link in links:
        text += (
            f"ID: <code>{link['id']}</code>\n"
            f"URL: {link['url']}\n\n"
        )

        keyboard.row(
            types.InlineKeyboardButton(
                f"🗑 Delete Link #{link['id']}",
                callback_data=f"admin_delete_link_{link['id']}"
            )
        )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_delete_link_")
)
def delete_link_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    try:
        link_id = int(call.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        bot.answer_callback_query(
            call.id,
            "Invalid link ID.",
            show_alert=True
        )
        return

    deleted = delete_link(link_id)

    if deleted:
        bot.answer_callback_query(
            call.id,
            "Link deleted successfully."
        )

        bot.send_message(
            call.message.chat.id,
            f"🗑 Link #{link_id} successfully deleted.\n\n"
            "Users ab is link ko unlock nahi kar sakenge."
        )
    else:
        bot.answer_callback_query(
            call.id,
            "Link nahi mila ya pehle hi delete ho chuka hai.",
            show_alert=True
        )


# ==========================================
# CANCEL COMMAND
# ==========================================

@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    user_id = message.from_user.id

    if user_id in admin_sessions:
        admin_sessions.pop(user_id, None)

        bot.reply_to(
            message,
            "❌ Current action cancelled.",
            reply_markup=admin_keyboard()
        )
