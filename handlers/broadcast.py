import time
import threading
from telebot import types

from bot import bot
from config import ADMIN_IDS, BROADCAST_DELAY, BROADCAST_BATCH_SIZE
from database import get_all_user_ids


broadcast_sessions = {}
broadcast_pending = {}
broadcast_cancelled = set()
broadcast_lock = threading.Lock()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def broadcast_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "✅ Confirm Broadcast",
            callback_data="broadcast_confirm"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data="broadcast_cancel"
        )
    )

    return keyboard


def broadcast_progress_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "⛔ Stop Broadcast",
            callback_data="broadcast_stop"
        )
    )

    return keyboard


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_broadcast"
)
def start_broadcast(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    broadcast_sessions[call.from_user.id] = True

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data="broadcast_cancel"
        )
    )

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "📢 <b>BROADCAST</b>\n\n"
        "Ab woh message ya media bhejo jo sabhi registered users ko send karna hai.\n\n"
        "Supported: Text, Photo, Video, Document, Audio, Voice, "
        "Animation, Sticker, Video Note, Contact, Location aur Venue.\n\n"
        "Message bhejne ke baad confirmation milega. "
        "Confirmation se pehle kisi user ko message nahi jayega.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.message_handler(
    func=lambda message: (
        message.from_user is not None
        and message.from_user.id in broadcast_sessions
    ),
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "animation",
        "sticker",
        "video_note",
        "contact",
        "location",
        "venue"
    ]
)
def receive_broadcast_message(message):
    admin_id = message.from_user.id

    if not is_admin(admin_id):
        broadcast_sessions.pop(admin_id, None)
        return

    if message.content_type == "text":
        if message.text.strip().lower() in ("/cancel", "cancel"):
            broadcast_sessions.pop(admin_id, None)

            bot.reply_to(
                message,
                "❌ Broadcast cancelled."
            )
            return

    broadcast_sessions.pop(admin_id, None)

    broadcast_pending[admin_id] = {
        "chat_id": message.chat.id,
        "message_id": message.message_id
    }

    try:
        total_users = len(get_all_user_ids())
    except Exception:
        total_users = 0

    preview_text = (
        "📢 <b>BROADCAST PREVIEW</b>\n\n"
        "Aapka message broadcast ke liye ready hai.\n\n"
        f"👥 Registered users: <b>{total_users}</b>\n\n"
        "Message preview upar dekho.\n"
        "Broadcast start karne ke liye Confirm dabao."
    )

    bot.send_message(
        message.chat.id,
        preview_text,
        reply_markup=broadcast_keyboard(),
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "broadcast_cancel"
)
def cancel_broadcast(call):
    admin_id = call.from_user.id

    if not is_admin(admin_id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    broadcast_sessions.pop(admin_id, None)
    broadcast_pending.pop(admin_id, None)

    with broadcast_lock:
        broadcast_cancelled.add(admin_id)

    bot.answer_callback_query(
        call.id,
        "Broadcast cancelled."
    )

    bot.send_message(
        call.message.chat.id,
        "❌ Broadcast cancelled. Koi naya broadcast start nahi hua."
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "broadcast_confirm"
)
def confirm_broadcast(call):
    admin_id = call.from_user.id

    if not is_admin(admin_id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    pending = broadcast_pending.pop(admin_id, None)

    if not pending:
        bot.answer_callback_query(
            call.id,
            "Koi pending broadcast nahi hai.",
            show_alert=True
        )
        return

    with broadcast_lock:
        broadcast_cancelled.discard(admin_id)

    bot.answer_callback_query(
        call.id,
        "Broadcast started!"
    )

    bot.send_message(
        call.message.chat.id,
        "📢 <b>BROADCAST STARTED</b>\n\n"
        "Messages send ho rahe hain.\n"
        "Beech mein rokne ke liye Stop button dabao.",
        reply_markup=broadcast_progress_keyboard(),
        parse_mode="HTML"
    )

    thread = threading.Thread(
        target=run_broadcast,
        args=(
            admin_id,
            pending["chat_id"],
            pending["message_id"],
            call.message.chat.id
        ),
        daemon=True
    )

    thread.start()


def run_broadcast(admin_id, source_chat_id, source_message_id, report_chat_id):
    try:
        user_ids = get_all_user_ids()
    except Exception as error:
        bot.send_message(
            report_chat_id,
            f"❌ Users load nahi ho paaye: {error}"
        )
        return

    total = len(user_ids)
    sent = 0
    failed = 0
    stopped = False

    batch_size = max(1, BROADCAST_BATCH_SIZE)
    delay = max(0, BROADCAST_DELAY)

    for index, user_id in enumerate(user_ids, start=1):
        with broadcast_lock:
            if admin_id in broadcast_cancelled:
                stopped = True
                break

        try:
            bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id
            )
            sent += 1

        except Exception:
            failed += 1

        if index % batch_size == 0:
            time.sleep(delay)

    not_sent = total - sent - failed

    with broadcast_lock:
        broadcast_cancelled.discard(admin_id)

    status = "⛔ <b>BROADCAST STOPPED</b>" if stopped else "✅ <b>BROADCAST COMPLETED</b>"

    report = (
        f"{status}\n\n"
        f"👥 Total users: <b>{total}</b>\n"
        f"✅ Successfully sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"⏳ Not sent: <b>{not_sent}</b>"
    )

    bot.send_message(
        report_chat_id,
        report,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "broadcast_stop"
)
def stop_broadcast(call):
    admin_id = call.from_user.id

    if not is_admin(admin_id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    with broadcast_lock:
        broadcast_cancelled.add(admin_id)

    bot.answer_callback_query(
        call.id,
        "Broadcast stop request received."
    )

    bot.send_message(
        call.message.chat.id,
        "⏳ Broadcast stop ho raha hai. Current send attempt ke baad ruk jayega."
    )
