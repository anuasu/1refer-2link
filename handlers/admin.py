import re
from telebot import types

from bot import bot

from config import ADMIN_IDS

from database import (
    add_links,
    get_active_links,
    get_links_count,
    delete_link
)


admin_sessions = {}


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


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "⛔ Only admin can access this panel."
        )
        return

    send_admin_panel(message.chat.id)


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

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data="admin_cancel_action"
        )
    )

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🔗 <b>ADD LINKS</b>\n\n"
        "Ek message mein ek ya multiple links bhejo.\n\n"
        "Example:\n"
        "https://example.com/link1\n"
        "https://example.com/link2\n"
        "https://t.me/example\n\n"
        "Links spaces ya new lines se separate kar sakte ho.\n"
        "Har valid link alag entry ke roop mein save hoga.",
        reply_markup=keyboard,
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
        and admin_sessions.get(message.from_user.id) == "waiting_for_links"
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
            "❌ Add Links cancelled."
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

    added_ids = add_links(
        links,
        user_id
    )

    admin_sessions.pop(user_id, None)

    if not added_ids:
        bot.send_message(
            message.chat.id,
            "❌ Links save nahi ho paaye. Dobara try karo."
        )
        return

    text = (
        "✅ <b>LINKS ADDED SUCCESSFULLY</b>\n\n"
        f"🔗 Links added: <b>{len(added_ids)}</b>\n"
        f"📊 Total active links: <b>{get_links_count()}</b>\n\n"
        "Ye links users ke Open Links section mein available honge."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )


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
        link_id = int(
            call.data.rsplit("_", 1)[1]
        )
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


@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    user_id = message.from_user.id

    if user_id in admin_sessions:
        admin_sessions.pop(user_id, None)

        bot.reply_to(
            message,
            "❌ Current action cancelled."
        )
