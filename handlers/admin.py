import logging
import secrets
import string
import re

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

try:
    LOCAL_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")


# =========================================================
# ADMIN HELPERS
# =========================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_only(message):
    if not message.from_user or not is_admin(message.from_user.id):
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

    keyboard.add(
        types.InlineKeyboardButton(
            "🟢 Auto Redeem: ON" if enabled else "🔴 Auto Redeem: OFF",
            callback_data="redeem_auto_toggle",
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 Set Channel",
            callback_data="redeem_auto_set_channel",
        ),
        types.InlineKeyboardButton(
            "📅 Set Initial Date & Time",
            callback_data="redeem_auto_set_time",
        ),
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⏱️ Repost Interval",
            callback_data="redeem_auto_set_interval",
        )
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
    channel_id = settings.get("channel_id") or CHANNEL_ID

    scheduled_at = settings.get("scheduled_at")

    # Backward compatibility with databases that only have post_time.
    post_time = settings.get("post_time") or "11:00"

    if scheduled_at:
        scheduled_display = str(scheduled_at)
    else:
        scheduled_display = (
            f"{post_time} (date not configured)"
        )

    interval = settings.get("repost_interval_hours") or 24
    reward = settings.get("reward_coins") or 10
    max_users = settings.get("max_users") or 100
    expiry = settings.get("expiry_hours") or 24

    status = "🟢 ENABLED" if enabled else "🔴 DISABLED"

    text = (
        "⚙️ <b>AUTO REDEEM SETTINGS</b>\n\n"
        f"Status: <b>{status}</b>\n"
        f"Channel ID: <code>{channel_id}</code>\n"
        f"Initial Date & Time: <b>{scheduled_display}</b>\n"
        f"Repost Interval: <b>{interval} hours</b>\n"
        f"Reward: <b>{reward} coins</b>\n"
        f"Maximum Users: <b>{max_users}</b>\n"
        f"Code Expiry: <b>{expiry} hours</b>\n\n"
        "ℹ️ Repost interval aur code expiry alag hain.\n"
        "Repost interval automatic post replace karne ka time hai.\n\n"
        "⚠️ Auto ON karne se pehle future date/time set karein.\n"
        "Bot ko channel mein post karne ki permission honi chahiye."
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


def valid_positive_int(value, minimum=1, maximum=2147483647):
    try:
        number = int(value)
    except (ValueError, TypeError):
        return None

    if not minimum <= number <= maximum:
        return None

    return number


def validate_channel_access(channel_id):
    try:
        chat = bot.get_chat(channel_id)

        member = bot.get_chat_member(
            channel_id,
            bot.get_me().id,
        )

        if member.status not in ("administrator", "creator"):
            return False, "Bot ko channel ka admin banao."

        if getattr(member, "can_post_messages", True) is False:
            return False, "Bot ke paas channel mein post karne ki permission nahi hai."

        return True, None

    except Exception:
        logger.exception("Channel access validation failed")
        return False, "Bot channel access nahi kar pa raha. Channel ID aur permissions check karo."


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


@bot.callback_query_handler(func=lambda call: call.data == "admin_home")
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

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_links")
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
            "🎁 <b>REDEEM CODE MANAGEMENT</b>\n\nChoose an option:",
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
        "Send reward coins per user.\nExample: <code>10</code>",
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
        bot.send_message(call.message.chat.id, "❌ Could not load redeem codes.")
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
        try:
            code = item["code"]
            reward = item["reward_coins"]
            max_users = item["max_users"]
            status = item["status"]
        except (KeyError, TypeError, IndexError):
            continue

        # Escape values before inserting them into HTML.
        code = str(code).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        status = str(status).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
        channel_id = settings.get("channel_id") or CHANNEL_ID

        if not channel_id:
            bot.answer_callback_query(
                call.id,
                "Pehle channel ID set karo.",
                show_alert=True,
            )
            return

        ok, error = validate_channel_access(channel_id)

        if not ok:
            bot.answer_callback_query(
                call.id,
                error or "Channel permissions check karo.",
                show_alert=True,
            )
            return

        # Do not turn on automatic posting without a future date/time.
        scheduled_at = settings.get("scheduled_at")

        if not scheduled_at:
            bot.answer_callback_query(
                call.id,
                "Pehle Initial Date & Time set karo.",
                show_alert=True,
            )
            return

        try:
            scheduled_dt = datetime.fromisoformat(str(scheduled_at))

            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(
                    tzinfo=LOCAL_TIMEZONE
                )

            if scheduled_dt <= datetime.now(LOCAL_TIMEZONE):
                bot.answer_callback_query(
                    call.id,
                    "Date/time future mein set karo.",
                    show_alert=True,
                )
                return

        except (ValueError, TypeError):
            bot.answer_callback_query(
                call.id,
                "Saved date/time invalid hai. Dobara set karo.",
                show_alert=True,
            )
            return

    saved = update_redeem_settings(auto_enabled=new_value)

    if not saved:
        bot.answer_callback_query(
            call.id,
            "Setting save nahi hui.",
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
        "Send the numeric channel ID.\n"
        "Example: <code>-1001234567890</code>\n\n"
        "Bot channel ka admin hona chahiye.",
    )


# =========================================================
# SET INITIAL DATE & TIME
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
        "📅 <b>SET INITIAL POST DATE & TIME</b>\n\n"
        f"Timezone: <code>{TIMEZONE}</code>\n\n"
        "Date aur time is format mein bhejo:\n"
        "<code>YYYY-MM-DD HH:MM</code>\n\n"
        "Example: <code>2026-12-25 17:00</code>\n\n"
        "Ye first automatic post ka scheduled time hoga.\n"
        "Time future mein hona chahiye.",
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
        types.InlineKeyboardButton("5 Hours", callback_data="redeem_interval_5"),
        types.InlineKeyboardButton("12 Hours", callback_data="redeem_interval_12"),
        types.InlineKeyboardButton("24 Hours", callback_data="redeem_interval_24"),
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
        "Automatic redeem post kitne hours baad replace karni hai?\n\n"
        "⚠️ Ye code expiry se alag setting hai.",
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
            "Interval hours mein bhejo.\n"
            "Examples: <code>3</code>, <code>8</code>, <code>36</code>\n"
            "Allowed: 1–87600 hours.",
        )
        return

    hours = valid_positive_int(value, 1, 87600)

    if hours is None:
        bot.answer_callback_query(call.id, "Invalid interval.", show_alert=True)
        return

    if not update_redeem_settings(repost_interval_hours=hours):
        bot.answer_callback_query(call.id, "Interval save nahi hua.", show_alert=True)
        return

    bot.answer_callback_query(call.id, f"Interval set: {hours} hours.")

    show_auto_settings(call.message.chat.id)


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
        "Har user ko kitne coins milenge?\n"
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
        "Maximum kitne users code redeem kar sakte hain?\n"
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
        "Code kitne hours tak valid rahega?\n"
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
        bot.answer_callback_query(call.id, "Code not found.", show_alert=True)
        return

    if code_data.get("is_auto"):
        bot.answer_callback_query(
            call.id,
            "Automatic code ko is button se manually post nahi kar sakte.",
            show_alert=True,
        )
        return

    channel_id = code_data.get("channel_id") or CHANNEL_ID

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

        bot.answer_callback_query(call.id, "Manual redeem post published!")

        bot.send_message(
            call.message.chat.id,
            "✅ Manual redeem code posted successfully.\n"
            "Automatic scheduler is tracking only its own posts.",
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
    ),
    content_types=["text"],
)
def handle_admin_input(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        admin_sessions.pop(user_id, None)
        return

    text = (message.text or "").strip()
    session = admin_sessions.get(user_id)

    if not session:
        return

    if text.lower() == "/cancel":
        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "❌ Action cancelled.",
            reply_markup=get_admin_keyboard(),
        )
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
            # database.py expects both URLs and admin ID.
            add_links(links, user_id)

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
                "❌ Could not save links. Database function check karo.",
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
                "❌ Invalid channel ID. Numeric channel ID bhejo.",
            )
            return

        ok, error = validate_channel_access(channel_id)

        if not ok:
            bot.send_message(message.chat.id, f"❌ {error}")
            return

        saved = update_redeem_settings(channel_id=channel_id)

        if saved:
            admin_sessions.pop(user_id, None)
            bot.send_message(message.chat.id, "✅ Automatic redeem channel updated.")
        else:
            bot.send_message(message.chat.id, "❌ Channel setting save nahi hui.")

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # INITIAL DATE & TIME
    # -----------------------------------------------------

    if action == "redeem_auto_time":
        try:
            naive_dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
            scheduled_dt = naive_dt.replace(tzinfo=LOCAL_TIMEZONE)
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Invalid format.\n"
                "Is format mein bhejo: <code>YYYY-MM-DD HH:MM</code>\n"
                "Example: <code>2026-12-25 17:00</code>",
                parse_mode="HTML",
            )
            return

        if scheduled_dt <= datetime.now(LOCAL_TIMEZONE):
            bot.send_message(
                message.chat.id,
                "❌ Date/time future mein hona chahiye. Dobara bhejo.",
            )
            return

        # scheduled_at support must exist in database.py.
        saved = update_redeem_settings(
            scheduled_at=scheduled_dt.isoformat(),
            post_time=scheduled_dt.strftime("%H:%M"),
            auto_enabled=0,
        )

        if not saved:
            bot.send_message(
                message.chat.id,
                "❌ Date/time save nahi hui. Database mein scheduled_at "
                "column aur update support verify karna hoga.",
            )
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ <b>Initial schedule saved!</b>\n\n"
            f"📅 Date: <code>{scheduled_dt.strftime('%Y-%m-%d')}</code>\n"
            f"🕒 Time: <code>{scheduled_dt.strftime('%H:%M')}</code>\n"
            f"🌐 Timezone: <code>{TIMEZONE}</code>\n\n"
            "Auto Redeem abhi OFF hai. Settings check karke ON kar sakte ho.",
            parse_mode="HTML",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # REPOST INTERVAL
    # -----------------------------------------------------

    if action == "redeem_auto_interval":
        hours = valid_positive_int(text, 1, 87600)

        if hours is None:
            bot.send_message(
                message.chat.id,
                "❌ Interval 1 se 87600 hours ke beech whole number hona chahiye.",
            )
            return

        saved = update_redeem_settings(repost_interval_hours=hours)

        if not saved:
            bot.send_message(message.chat.id, "❌ Interval save nahi hua.")
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            f"✅ Repost interval set to {hours} hours.",
        )

        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO REWARD
    # -----------------------------------------------------

    if action == "redeem_auto_reward":
        reward = valid_positive_int(text)

        if reward is None:
            bot.send_message(
                message.chat.id,
                "❌ Reward positive whole number hona chahiye.",
            )
            return

        saved = update_redeem_settings(reward_coins=reward)

        if not saved:
            bot.send_message(message.chat.id, "❌ Reward save nahi hua.")
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(message.chat.id, "✅ Reward updated.")
        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO MAX USERS
    # -----------------------------------------------------

    if action == "redeem_auto_max":
        max_users = valid_positive_int(text)

        if max_users is None:
            bot.send_message(
                message.chat.id,
                "❌ Maximum users positive whole number hona chahiye.",
            )
            return

        saved = update_redeem_settings(max_users=max_users)

        if not saved:
            bot.send_message(message.chat.id, "❌ Maximum users save nahi hue.")
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(message.chat.id, "✅ Maximum users updated.")
        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # AUTO CODE EXPIRY
    # -----------------------------------------------------

    if action == "redeem_auto_expiry":
        expiry = valid_positive_int(text)

        if expiry is None:
            bot.send_message(
                message.chat.id,
                "❌ Expiry positive whole number of hours honi chahiye.",
            )
            return

        saved = update_redeem_settings(expiry_hours=expiry)

        if not saved:
            bot.send_message(message.chat.id, "❌ Code expiry save nahi hui.")
            return

        admin_sessions.pop(user_id, None)

        bot.send_message(message.chat.id, "✅ Code expiry updated.")
        show_auto_settings(message.chat.id)
        return

    # -----------------------------------------------------
    # MANUAL CODE CREATION
    # -----------------------------------------------------

    if action == "manual_code":
        step = session.get("step")

        if step == "code":
            code = text.upper()

            if not 1 <= len(code) <= 50:
                bot.send_message(message.chat.id, "❌ Code 1–50 characters ka hona chahiye.")
                return

            if not re.fullmatch(r"[A-Z0-9_-]+", code):
                bot.send_message(
                    message.chat.id,
                    "❌ Sirf letters, numbers, underscore aur hyphen use karo.",
                )
                return

            if get_redeem_code(code):
                bot.send_message(
                    message.chat.id,
                    "❌ Ye code pehle se exist karta hai. Dusra code bhejo.",
                )
                return

            session["code"] = code
            session["step"] = "reward"

            bot.send_message(message.chat.id, "🪙 Reward coins bhejo.")
            return

        if step == "reward":
            reward = valid_positive_int(text)

            if reward is None:
                bot.send_message(message.chat.id, "❌ Reward positive number hona chahiye.")
                return

            session["reward"] = reward
            session["step"] = "max_users"

            bot.send_message(message.chat.id, "👥 Maximum users bhejo.")
            return

        if step == "max_users":
            max_users = valid_positive_int(text)

            if max_users is None:
                bot.send_message(message.chat.id, "❌ Maximum users positive number hona chahiye.")
                return

            session["max_users"] = max_users
            session["step"] = "expiry"

            bot.send_message(message.chat.id, "⌛ Code expiry hours mein bhejo.")
            return

        if step == "expiry":
            expiry_hours = valid_positive_int(text)

            if expiry_hours is None:
                bot.send_message(message.chat.id, "❌ Expiry positive number honi chahiye.")
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
                bot.send_message(message.chat.id, "❌ Code create nahi hua. Logs check karo.")
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
            reward = valid_positive_int(text)

            if reward is None:
                bot.send_message(message.chat.id, "❌ Reward positive number hona chahiye.")
                return

            session["reward"] = reward
            session["step"] = "max_users"

            bot.send_message(message.chat.id, "👥 Maximum users bhejo.")
            return

        if step == "max_users":
            max_users = valid_positive_int(text)

            if max_users is None:
                bot.send_message(message.chat.id, "❌ Maximum users positive number hona chahiye.")
                return

            session["max_users"] = max_users
            session["step"] = "expiry"

            bot.send_message(message.chat.id, "⌛ Expiry hours mein bhejo.")
            return

        if step == "expiry":
            expiry_hours = valid_positive_int(text)

            if expiry_hours is None:
                bot.send_message(message.chat.id, "❌ Expiry positive number honi chahiye.")
                return

            reward = session["reward"]
            max_users = session["max_users"]

            code = None

            for _ in range(20):
                candidate = generate_random_code()

                if not get_redeem_code(candidate):
                    code = candidate
                    break

            if not code:
                admin_sessions.pop(user_id, None)
                bot.send_message(
                    message.chat.id,
                    "❌ Unique code generate nahi hua. Dobara try karo.",
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
                bot.send_message(message.chat.id, "❌ Generated code save nahi hua.")
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
        "⚠️ Admin action identify nahi hua. /cancel bhejkar dobara try karo.",
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
        "Broadcast feature ke liye handlers.broadcast mein configured command use karo.",
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
        "Backup commands ke liye handlers.backup mein configured feature use karo.",
        parse_mode="HTML",
    )
