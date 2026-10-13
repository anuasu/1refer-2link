import logging
import secrets
import string

from datetime import datetime
from zoneinfo import ZoneInfo

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


# =========================================================
# ADMIN HELPERS
# =========================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_only(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Only admins can use this command.")
        return False

    return True


def get_admin_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton(
            "🔗 Add Links",
            callback_data="admin_add_links",
        ),
        types.InlineKeyboardButton(
            "🎁 Redeem Management",
            callback_data="admin_redeem_management",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 Broadcast",
            callback_data="admin_broadcast",
        ),
        types.InlineKeyboardButton(
            "💾 Backup & Recovery",
            callback_data="admin_backup",
        ),
    )

    return keyboard


def get_redeem_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton(
            "➕ Create Manual Code",
            callback_data="redeem_create_manual",
        ),
        types.InlineKeyboardButton(
            "🎲 Generate Random Code",
            callback_data="redeem_generate_random",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📋 View Codes",
            callback_data="redeem_view_codes",
        ),
        types.InlineKeyboardButton(
            "⚙️ Auto Code Settings",
            callback_data="redeem_auto_settings",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔙 Admin Panel",
            callback_data="admin_home",
        )
    )

    return keyboard


def get_auto_settings_keyboard(settings):
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    enabled = bool(settings.get("auto_enabled", 0))

    toggle_text = (
        "🟢 Auto Redeem: ON"
        if enabled
        else "🔴 Auto Redeem: OFF"
    )

    keyboard.add(
        types.InlineKeyboardButton(
            toggle_text,
            callback_data="redeem_auto_toggle",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 Set Channel",
            callback_data="redeem_auto_set_channel",
        ),
        types.InlineKeyboardButton(
            "🕒 Initial Post Time",
            callback_data="redeem_auto_set_time",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⏱️ Repost Interval",
            callback_data="redeem_auto_set_interval",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🪙 Set Reward",
            callback_data="redeem_auto_set_reward",
        ),
        types.InlineKeyboardButton(
            "👥 Set Max Users",
            callback_data="redeem_auto_set_max",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⌛ Set Code Expiry",
            callback_data="redeem_auto_set_expiry",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔙 Redeem Menu",
            callback_data="admin_redeem_management",
        )
    )

    return keyboard


def show_auto_settings(chat_id, message_id=None):
    settings = get_redeem_settings() or {}

    enabled = bool(settings.get("auto_enabled", 0))

    channel_id = (
        settings.get("channel_id")
        or CHANNEL_ID
    )

    post_time = settings.get("post_time") or "11:00"

    interval = settings.get("repost_interval_hours") or 24

    reward = settings.get("reward_coins") or 10

    max_users = settings.get("max_users") or 100

    expiry = settings.get("expiry_hours") or 24

    status = "🟢 ENABLED" if enabled else "🔴 DISABLED"

    text = (
        "⚙️ <b>AUTO REDEEM SETTINGS</b>\n\n"
        f"Status: <b>{status}</b>\n"
        f"Channel ID: <code>{channel_id}</code>\n"
        f"Initial Post Time: <b>{post_time}</b>\n"
        f"Repost Interval: <b>{interval} hours</b>\n"
        f"Reward: <b>{reward} coins</b>\n"
        f"Maximum Users: <b>{max_users}</b>\n"
        f"Code Expiry: <b>{expiry} hours</b>\n\n"
        "ℹ️ Repost interval aur code expiry alag settings hain.\n"
        "Repost interval decide karta hai ki next automatic post "
        "kab publish hogi.\n\n"
        "⚠️ Auto ON karne ke liye bot ko channel mein post karne "
        "ki permission honi chahiye."
    )

    keyboard = get_auto_settings_keyboard(settings)

    if message_id:
        try:
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception:
            logger.exception("Could not edit auto settings message")

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


def ask_for_admin_input(call, action, prompt):
    admin_sessions[call.from_user.id] = {
        "action": action,
        "chat_id": call.message.chat.id,
    }

    bot.send_message(
        call.message.chat.id,
        prompt,
        parse_mode="HTML",
    )


def generate_random_code(length=12):
    characters = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@bot.message_handler(commands=["admin", "panel"])
def admin_panel(message):
    if not admin_only(message):
        return

    bot.send_message(
        message.chat.id,
        "🛠️ <b>ADMIN PANEL</b>\n\nSelect an option:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_home"
)
def admin_home_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "⛔ Only admins can access this panel.",
            show_alert=True,
        )
        return

    bot.answer_callback_query(call.id)

    try:
        bot.edit_message_text(
            "🛠️ <b>ADMIN PANEL</b>\n\nSelect an option:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            "🛠️ <b>ADMIN PANEL</b>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
        )


# =========================================================
# ADD LINKS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "admin_add_links"
)
def admin_add_links_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    admin_sessions[call.from_user.id] = {
        "action": "add_links",
        "chat_id": call.message.chat.id,
    }

    bot.send_message(
        call.message.chat.id,
        "🔗 <b>ADD LINKS</b>\n\n"
        "Send links, one per line.\n\n"
        "Example:\n"
        "<code>https://example.com/link1\n"
        "https://example.com/link2</code>\n\n"
        "Send /cancel to cancel.",
        parse_mode="HTML",
    )


# =========================================================
# REDEEM MANAGEMENT MENU
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "admin_redeem_management"
)
def redeem_management_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    try:
        bot.edit_message_text(
            "🎁 <b>REDEEM CODE MANAGEMENT</b>\n\n"
            "Choose an option:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_redeem_menu_keyboard(),
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            "🎁 <b>REDEEM CODE MANAGEMENT</b>",
            parse_mode="HTML",
            reply_markup=get_redeem_menu_keyboard(),
        )


# =========================================================
# CREATE MANUAL REDEEM CODE
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_create_manual"
)
def redeem_create_manual_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    admin_sessions[call.from_user.id] = {
        "action": "manual_code",
        "step": "code",
        "chat_id": call.message.chat.id,
    }

    bot.send_message(
        call.message.chat.id,
        "🎁 <b>CREATE MANUAL REDEEM CODE</b>\n\n"
        "Send the code you want to create.\n"
        "Example: <code>WELCOME2026</code>\n\n"
        "Send /cancel to cancel.",
        parse_mode="HTML",
    )


# =========================================================
# GENERATE RANDOM REDEEM CODE
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_generate_random"
)
def redeem_generate_random_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    admin_sessions[call.from_user.id] = {
        "action": "random_code",
        "step": "reward",
        "chat_id": call.message.chat.id,
    }

    bot.send_message(
        call.message.chat.id,
        "🎲 <b>GENERATE RANDOM CODE</b>\n\n"
        "Send reward coins per user.\n"
        "Example: <code>10</code>",
        parse_mode="HTML",
    )


# =========================================================
# VIEW REDEEM CODES
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_view_codes"
)
def redeem_view_codes_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    try:
        codes = get_redeem_codes()
    except Exception:
        logger.exception("Could not retrieve redeem codes")
        bot.send_message(
            call.message.chat.id,
            "❌ Could not load redeem codes.",
        )
        return

    if not codes:
        bot.send_message(
            call.message.chat.id,
            "📋 No redeem codes found.",
            reply_markup=get_redeem_menu_keyboard(),
        )
        return

    lines = ["📋 <b>REDEEM CODES</b>\n"]

    for item in codes[:30]:
        if isinstance(item, dict):
            code = item.get("code", "Unknown")
            reward = item.get("reward_coins", "?")
            max_users = item.get("max_users", "?")
            status = item.get("status", "active")
        else:
            try:
                code = item["code"]
                reward = item["reward_coins"]
                max_users = item["max_users"]
                status = item["status"]
            except Exception:
                continue

        lines.append(
            f"🎟️ <code>{code}</code>\n"
            f"🪙 Reward: {reward} | 👥 Max: {max_users}\n"
            f"Status: {status}\n"
        )

    bot.send_message(
        call.message.chat.id,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_redeem_menu_keyboard(),
    )


# =========================================================
# AUTO REDEEM SETTINGS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_settings"
)
def redeem_auto_settings_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    show_auto_settings(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


# =========================================================
# AUTO REDEEM ON/OFF
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_toggle"
)
def redeem_auto_toggle_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    settings = get_redeem_settings() or {}

    new_value = 0 if settings.get("auto_enabled", 0) else 1

    if new_value:
        channel_id = (
            settings.get("channel_id")
            or CHANNEL_ID
        )

        try:
            bot.get_chat(channel_id)
        except Exception:
            bot.answer_callback_query(
                call.id,
                "❌ Bot cannot access the configured channel. "
                "Check the channel ID and bot permissions.",
                show_alert=True,
            )
            return

    saved = update_redeem_settings(
        auto_enabled=new_value,
    )

    if not saved:
        bot.answer_callback_query(
            call.id,
            "❌ Could not update setting.",
            show_alert=True,
        )
        return

    bot.answer_callback_query(
        call.id,
        "Auto Redeem enabled!" if new_value else "Auto Redeem disabled!",
    )

    show_auto_settings(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


# =========================================================
# SET CHANNEL
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_channel"
)
def redeem_auto_set_channel_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    ask_for_admin_input(
        call,
        "redeem_auto_channel",
        "📢 <b>SET REDEEM CHANNEL</b>\n\n"
        "Send the channel ID.\n"
        "Example: <code>-1001234567890</code>\n\n"
        "The bot must be an admin in that channel.",
    )


# =========================================================
# SET INITIAL POST TIME
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_time"
)
def redeem_auto_set_time_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    ask_for_admin_input(
        call,
        "redeem_auto_time",
        "🕒 <b>SET INITIAL POST TIME</b>\n\n"
        "Send time in 24-hour format, using India/local timezone "
        "configured in TIMEZONE.\n\n"
        "Examples: <code>09:00</code>, <code>18:30</code>",
    )


# =========================================================
# SET REPOST INTERVAL
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_interval"
)
def redeem_auto_set_interval_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    keyboard = types.InlineKeyboardMarkup(row_width=3)

    keyboard.add(
        types.InlineKeyboardButton(
            "5 Hours",
            callback_data="redeem_interval_5",
        ),
        types.InlineKeyboardButton(
            "12 Hours",
            callback_data="redeem_interval_12",
        ),
        types.InlineKeyboardButton(
            "24 Hours",
            callback_data="redeem_interval_24",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✍️ Custom Hours",
            callback_data="redeem_interval_custom",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="redeem_auto_settings",
        )
    )

    bot.send_message(
        call.message.chat.id,
        "⏱️ <b>SET REPOST INTERVAL</b>\n\n"
        "Select how many hours to wait before replacing "
        "the previous automatic redeem post.\n\n"
        "ℹ️ This is separate from code expiry.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("redeem_interval_")
)
def redeem_interval_preset_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    value = call.data.replace("redeem_interval_", "", 1)

    if value == "custom":
        bot.answer_callback_query(call.id)

        ask_for_admin_input(
            call,
            "redeem_auto_interval",
            "✍️ <b>CUSTOM REPOST INTERVAL</b>\n\n"
            "Send the interval in hours.\n"
            "Examples: <code>3</code>, <code>8</code>, <code>36</code>\n\n"
            "Allowed range: 1 to 87600 hours.",
        )
        return

    try:
        hours = int(value)
    except ValueError:
        bot.answer_callback_query(
            call.id,
            "Invalid interval.",
            show_alert=True,
        )
        return

    if not 1 <= hours <= 87600:
        bot.answer_callback_query(
            call.id,
            "Interval must be between 1 and 87600 hours.",
            show_alert=True,
        )
        return

    saved = update_redeem_settings(
        repost_interval_hours=hours,
    )

    if not saved:
        bot.answer_callback_query(
            call.id,
            "Could not save interval.",
            show_alert=True,
        )
        return

    bot.answer_callback_query(
        call.id,
        f"Repost interval set to {hours} hours.",
    )

    show_auto_settings(
        chat_id=call.message.chat.id,
    )


# =========================================================
# SET REWARD
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_reward"
)
def redeem_auto_set_reward_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    ask_for_admin_input(
        call,
        "redeem_auto_reward",
        "🪙 <b>SET REWARD</b>\n\n"
        "Send the number of coins each user receives.\n"
        "Example: <code>10</code>",
    )


# =========================================================
# SET MAX USERS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_max"
)
def redeem_auto_set_max_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    ask_for_admin_input(
        call,
        "redeem_auto_max",
        "👥 <b>SET MAX USERS</b>\n\n"
        "Send the maximum number of users allowed to redeem.\n"
        "Example: <code>100</code>",
    )


# =========================================================
# SET CODE EXPIRY
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "redeem_auto_set_expiry"
)
def redeem_auto_set_expiry_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    ask_for_admin_input(
        call,
        "redeem_auto_expiry",
        "⌛ <b>SET CODE EXPIRY</b>\n\n"
        "Send how many hours the redeem code should remain valid.\n"
        "Example: <code>24</code>",
    )


# =========================================================
# POST MANUAL CODE TO CHANNEL
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("redeem_post_")
)
def redeem_post_manual_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    code = call.data[len("redeem_post_"):]

    code_data = get_redeem_code(code)

    if not code_data:
        bot.answer_callback_query(
            call.id,
            "Code not found.",
            show_alert=True,
        )
        return

    channel_id = (
        code_data.get("channel_id")
        or CHANNEL_ID
    )

    message_text = (
        "🎁 <b>REDEEM CODE</b>\n\n"
        f"🎟️ Code: <code>{code}</code>\n"
        f"🪙 Reward: <b>{code_data.get('reward_coins', 0)} coins</b>\n"
        f"👥 Maximum Users: <b>{code_data.get('max_users', 0)}</b>\n\n"
        "🤖 Open the bot and select Redeem Code to claim your reward."
    )

    try:
        bot.send_message(
            chat_id=channel_id,
            text=message_text,
            parse_mode="HTML",
        )

        bot.answer_callback_query(
            call.id,
            "Manual redeem post published!",
        )

        bot.send_message(
            call.message.chat.id,
            "✅ Manual redeem code posted successfully.\n"
            "This post will not be deleted by the automatic repost scheduler.",
        )

    except Exception:
        logger.exception("Could not publish manual redeem post")

        bot.answer_callback_query(
            call.id,
            "Failed to post. Check bot channel permissions.",
            show_alert=True,
        )


# =========================================================
# ADMIN INPUT HANDLER
# =========================================================

@bot.message_handler(
    func=lambda message: (
        message.from_user is not None
        and message.from_user.id in admin_sessions
    )
)
def handle_admin_input(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        admin_sessions.pop(user_id, None)
        return

    text = (message.text or "").strip()

    if text.lower() == "/cancel":
        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "❌ Action cancelled.",
            reply_markup=get_admin_keyboard(),
        )
        return

    session = admin_sessions.get(user_id)

    if not session:
        return

    action = session.get("action")

    # -----------------------------------------------------
    # ADD LINKS
    # -----------------------------------------------------

    if action == "add_links":
        links = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        if not links:
            bot.send_message(message.chat.id, "❌ No links received.")
            return

        try:
            add_links(links)

            admin_sessions.pop(user_id, None)

            bot.send_message(
                message.chat.id,
                f"✅ Submitted {len(links)} link(s).",
                reply_markup=get_admin_keyboard(),
            )

        except Exception:
            logger.exception("Could not add links")

            bot.send_message(
                message.chat.id,
                "❌ Could not save links. Check the link database function.",
            )

        return

    # -----------------------------------------------------
    # AUTO CHANNEL
    # -----------------------------------------------------

    if action == "redeem_auto_channel":
        try:
            channel_id = int(text)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Invalid channel ID. Send a numeric channel ID.",
            )
            return

        try:
            bot.get_chat(channel_id)
        except Exception:
            bot.send_message(
                message.chat.id,
                "❌ The bot cannot access this channel. "
                "Check the channel ID and make the bot an admin.",
            )
            return

        saved = update_redeem_settings(
            channel_id=channel_id,
        )

        admin_sessions.pop(user_id, None)

        if saved:
            bot.send_message(
                message.chat.id,
                "✅ Automatic redeem channel updated.",
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Could not save channel settings.",
            )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # INITIAL POST TIME
    # -----------------------------------------------------

    if action == "redeem_auto_time":
        try:
            datetime.strptime(text, "%H:%M")
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Invalid time. Use HH:MM format, for example 11:00.",
            )
            return

        saved = update_redeem_settings(
            post_time=text,
        )

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ Initial post time updated."
            if saved
            else "❌ Could not save the post time.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # REPOST INTERVAL
    # -----------------------------------------------------

    if action == "redeem_auto_interval":
        try:
            hours = int(text)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Send the interval as a whole number of hours.",
            )
            return

        if not 1 <= hours <= 87600:
            bot.send_message(
                message.chat.id,
                "❌ Interval must be between 1 and 87600 hours.",
            )
            return

        saved = update_redeem_settings(
            repost_interval_hours=hours,
        )

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            f"✅ Repost interval set to {hours} hours."
            if saved
            else "❌ Could not save the repost interval.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO REWARD
    # -----------------------------------------------------

    if action == "redeem_auto_reward":
        try:
            reward = int(text)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Reward must be a number.",
            )
            return

        if reward <= 0:
            bot.send_message(
                message.chat.id,
                "❌ Reward must be greater than zero.",
            )
            return

        saved = update_redeem_settings(
            reward_coins=reward,
        )

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ Reward updated."
            if saved
            else "❌ Could not save reward.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO MAX USERS
    # -----------------------------------------------------

    if action == "redeem_auto_max":
        try:
            max_users = int(text)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Maximum users must be a number.",
            )
            return

        if max_users <= 0:
            bot.send_message(
                message.chat.id,
                "❌ Maximum users must be greater than zero.",
            )
            return

        saved = update_redeem_settings(
            max_users=max_users,
        )

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ Maximum users updated."
            if saved
            else "❌ Could not save maximum users.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO CODE EXPIRY
    # -----------------------------------------------------

    if action == "redeem_auto_expiry":
        try:
            expiry = int(text)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Expiry must be a number of hours.",
            )
            return

        if expiry <= 0:
            bot.send_message(
                message.chat.id,
                "❌ Expiry must be greater than zero.",
            )
            return

        saved = update_redeem_settings(
            expiry_hours=expiry,
        )

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ Code expiry updated."
            if saved
            else "❌ Could not save code expiry.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # MANUAL CODE CREATION
    # -----------------------------------------------------

    if action == "manual_code":
        step = session.get("step")

        if step == "code":
            code = text.upper()

            if not code or len(code) > 50:
                bot.send_message(
                    message.chat.id,
                    "❌ Code must contain 1–50 characters.",
                )
                return

            if not all(
                character in string.ascii_uppercase
                + string.digits
                + "_-"
                for character in code
            ):
                bot.send_message(
                    message.chat.id,
                    "❌ Use only letters, numbers, underscores or hyphens.",
                )
                return

            if get_redeem_code(code):
                bot.send_message(
                    message.chat.id,
                    "❌ This code already exists. Send another code.",
                )
                return

            session["code"] = code
            session["step"] = "reward"

            bot.send_message(
                message.chat.id,
                "🪙 Send the reward amount in coins.",
            )
            return

        if step == "reward":
            try:
                reward = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Reward must be a number.",
                )
                return

            if reward <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Reward must be greater than zero.",
                )
                return

            session["reward"] = reward
            session["step"] = "max_users"

            bot.send_message(
                message.chat.id,
                "👥 Send the maximum number of users.",
            )
            return

        if step == "max_users":
            try:
                max_users = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Maximum users must be a number.",
                )
                return

            if max_users <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Maximum users must be greater than zero.",
                )
                return

            session["max_users"] = max_users
            session["step"] = "expiry"

            bot.send_message(
                message.chat.id,
                "⌛ Send expiry in hours.",
            )
            return

        if step == "expiry":
            try:
                expiry_hours = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Expiry must be a number of hours.",
                )
                return

            if expiry_hours <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Expiry must be greater than zero.",
                )
                return

            code = session["code"]
            reward = session["reward"]
            max_users = session["max_users"]

            expires_at = generate_redeem_expiry(expiry_hours)

            try:
                created = create_redeem_code(
                    code=code,
                    reward_coins=reward,
                    max_users=max_users,
                    expires_at=expires_at,
                    created_by=user_id,
                    is_auto=False,
                    channel_id=CHANNEL_ID,
                )
            except Exception:
                logger.exception("Could not create manual redeem code")
                created = False

            admin_sessions.pop(user_id, None)

            if not created:
                bot.send_message(
                    message.chat.id,
                    "❌ Could not create the code. Check the database logs.",
                )
                return

            keyboard = types.InlineKeyboardMarkup()

            keyboard.add(
                types.InlineKeyboardButton(
                    "📢 Post to Channel",
                    callback_data=f"redeem_post_{code}",
                )
            )

            bot.send_message(
                message.chat.id,
                "✅ <b>MANUAL REDEEM CODE CREATED</b>\n\n"
                f"🎟️ Code: <code>{code}</code>\n"
                f"🪙 Reward: {reward} coins\n"
                f"👥 Maximum Users: {max_users}\n"
                f"⌛ Expiry: {expiry_hours} hours",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

            return

    # -----------------------------------------------------
    # RANDOM CODE CREATION
    # -----------------------------------------------------

    if action == "random_code":
        step = session.get("step")

        if step == "reward":
            try:
                reward = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Reward must be a number.",
                )
                return

            if reward <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Reward must be greater than zero.",
                )
                return

            session["reward"] = reward
            session["step"] = "max_users"

            bot.send_message(
                message.chat.id,
                "👥 Send the maximum number of users.",
            )
            return

        if step == "max_users":
            try:
                max_users = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Maximum users must be a number.",
                )
                return

            if max_users <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Maximum users must be greater than zero.",
                )
                return

            session["max_users"] = max_users
            session["step"] = "expiry"

            bot.send_message(
                message.chat.id,
                "⌛ Send expiry in hours.",
            )
            return

        if step == "expiry":
            try:
                expiry_hours = int(text)
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "❌ Expiry must be a number of hours.",
                )
                return

            if expiry_hours <= 0:
                bot.send_message(
                    message.chat.id,
                    "❌ Expiry must be greater than zero.",
                )
                return

            reward = session["reward"]
            max_users = session["max_users"]

            code = None

            for _ in range(10):
                candidate = generate_random_code()

                if not get_redeem_code(candidate):
                    code = candidate
                    break

            if not code:
                admin_sessions.pop(user_id, None)

                bot.send_message(
                    message.chat.id,
                    "❌ Could not generate a unique code. Try again.",
                )
                return

            expires_at = generate_redeem_expiry(expiry_hours)

            try:
                created = create_redeem_code(
                    code=code,
                    reward_coins=reward,
                    max_users=max_users,
                    expires_at=expires_at,
                    created_by=user_id,
                    is_auto=False,
                    channel_id=CHANNEL_ID,
                )
            except Exception:
                logger.exception("Could not create random redeem code")
                created = False

            admin_sessions.pop(user_id, None)

            if not created:
                bot.send_message(
                    message.chat.id,
                    "❌ Could not save the generated code.",
                )
                return

            keyboard = types.InlineKeyboardMarkup()

            keyboard.add(
                types.InlineKeyboardButton(
                    "📢 Post to Channel",
                    callback_data=f"redeem_post_{code}",
                )
            )

            bot.send_message(
                message.chat.id,
                "✅ <b>RANDOM REDEEM CODE CREATED</b>\n\n"
                f"🎟️ Code: <code>{code}</code>\n"
                f"🪙 Reward: {reward} coins\n"
                f"👥 Maximum Users: {max_users}\n"
                f"⌛ Expiry: {expiry_hours} hours",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

            return

    bot.send_message(
        message.chat.id,
        "⚠️ I couldn't identify that admin action. Use /cancel and try again.",
    )


# =========================================================
# BROADCAST & BACKUP BUTTONS
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "admin_broadcast"
)
def admin_broadcast_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "📢 <b>Broadcast</b>\n\n"
        "Use the broadcast command/feature configured in "
        "<code>handlers.broadcast</code>.",
        parse_mode="HTML",
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_backup"
)
def admin_backup_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only!", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "💾 <b>Backup & Recovery</b>\n\n"
        "Use the backup commands configured in "
        "<code>handlers.backup</code>.",
        parse_mode="HTML",
    )
