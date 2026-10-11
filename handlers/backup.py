import os
import glob
import shutil
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from telebot import types

from bot import bot
from config import (
    ADMIN_IDS,
    DATABASE_FILE,
    BACKUP_HOUR,
    BACKUP_MINUTE,
    TIMEZONE
)


backup_sessions = {}
recovery_lock = threading.Lock()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_backup_directory():
    directory = "backups"
    os.makedirs(directory, exist_ok=True)
    return directory


def create_backup():
    if not os.path.exists(DATABASE_FILE):
        raise FileNotFoundError("Database file nahi mili.")

    backup_directory = get_backup_directory()

    timestamp = datetime.now(
        ZoneInfo(TIMEZONE)
    ).strftime("%Y-%m-%d_%H-%M-%S")

    backup_path = os.path.join(
        backup_directory,
        f"refer_earn_backup_{timestamp}.db"
    )

    source = sqlite3.connect(DATABASE_FILE)
    destination = sqlite3.connect(backup_path)

    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    return backup_path


def backup_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📦 Create Backup",
            callback_data="backup_create"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📂 Backup History",
            callback_data="backup_history"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "♻️ Recover Database",
            callback_data="backup_recovery"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data="admin_cancel_action"
        )
    )

    return keyboard


def send_backup_menu(chat_id):
    bot.send_message(
        chat_id,
        "💾 <b>BACKUP & RECOVERY</b>\n\n"
        "📦 Create Backup — Current database ka backup.\n"
        "📂 Backup History — Available backup files.\n"
        "♻️ Recover Database — Uploaded backup se database replace.\n\n"
        "⏰ Automatic backup: Har raat 12:00 AM IST.",
        reply_markup=backup_keyboard(),
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_backup"
)
def open_backup_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)
    send_backup_menu(call.message.chat.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "backup_create"
)
def manual_backup(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Backup create ho raha hai..."
    )

    try:
        backup_path = create_backup()

        with open(backup_path, "rb") as backup_file:
            bot.send_document(
                call.message.chat.id,
                backup_file,
                caption=(
                    "✅ <b>DATABASE BACKUP READY</b>\n\n"
                    f"📁 File: <code>{os.path.basename(backup_path)}</code>"
                ),
                parse_mode="HTML"
            )

    except Exception as error:
        bot.send_message(
            call.message.chat.id,
            f"❌ Backup failed:\n<code>{error}</code>",
            parse_mode="HTML"
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "backup_history"
)
def backup_history(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)

    files = sorted(
        glob.glob(
            os.path.join(
                get_backup_directory(),
                "*.db"
            )
        ),
        key=os.path.getmtime,
        reverse=True
    )

    if not files:
        bot.send_message(
            call.message.chat.id,
            "📭 Abhi koi backup file available nahi hai."
        )
        return

    keyboard = types.InlineKeyboardMarkup()

    text = "📂 <b>BACKUP HISTORY</b>\n\n"

    for path in files[:20]:
        filename = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024)

        text += (
            f"📄 <code>{filename}</code>\n"
            f"💾 Size: {size_mb:.2f} MB\n\n"
        )

        keyboard.row(
            types.InlineKeyboardButton(
                f"📤 Send {filename[:25]}",
                callback_data=f"backup_send_{filename}"
            )
        )

    bot.send_message(
        call.message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("backup_send_")
)
def send_existing_backup(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    filename = call.data[len("backup_send_"):]

    if os.path.basename(filename) != filename:
        bot.answer_callback_query(
            call.id,
            "Invalid filename.",
            show_alert=True
        )
        return

    backup_path = os.path.join(
        get_backup_directory(),
        filename
    )

    if not os.path.isfile(backup_path):
        bot.answer_callback_query(
            call.id,
            "Backup file nahi mili.",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)

    try:
        with open(backup_path, "rb") as backup_file:
            bot.send_document(
                call.message.chat.id,
                backup_file,
                caption=f"📦 Backup: <code>{filename}</code>",
                parse_mode="HTML"
            )

    except Exception as error:
        bot.send_message(
            call.message.chat.id,
            f"❌ File send nahi hui:\n<code>{error}</code>",
            parse_mode="HTML"
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "backup_recovery"
)
def start_recovery(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    backup_sessions[call.from_user.id] = True

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "❌ Cancel Recovery",
            callback_data="backup_recovery_cancel"
        )
    )

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "♻️ <b>DATABASE RECOVERY</b>\n\n"
        "Apni backup .db file document ke roop mein bhejo.\n\n"
        "⚠️ Recovery existing database ko replace karegi. "
        "Current database ka safety backup nahi banega.\n\n"
        "Recovery se pehle sahi backup file select karna.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "backup_recovery_cancel"
)
def cancel_recovery(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "Access denied!",
            show_alert=True
        )
        return

    backup_sessions.pop(call.from_user.id, None)

    bot.answer_callback_query(
        call.id,
        "Recovery cancelled."
    )

    bot.send_message(
        call.message.chat.id,
        "❌ Database recovery cancelled."
    )


@bot.message_handler(
    content_types=["document"],
    func=lambda message: (
        message.from_user is not None
        and message.from_user.id in backup_sessions
    )
)
def receive_recovery_file(message):
    admin_id = message.from_user.id

    if not is_admin(admin_id):
        backup_sessions.pop(admin_id, None)
        return

    document = message.document

    if not document.file_name or not document.file_name.lower().endswith(".db"):
        bot.reply_to(
            message,
            "❌ Sirf .db backup file bhejo."
        )
        return

    backup_sessions.pop(admin_id, None)

    bot.reply_to(
        message,
        "⏳ Backup validate ho raha hai..."
    )

    thread = threading.Thread(
        target=recover_database,
        args=(
            message.chat.id,
            document.file_id,
            document.file_name
        ),
        daemon=True
    )

    thread.start()


def recover_database(chat_id, file_id, filename):
    temporary_path = None

    try:
        file_info = bot.get_file(file_id)
        file_bytes = bot.download_file(file_info.file_path)

        backup_directory = get_backup_directory()

        temporary_path = os.path.join(
            backup_directory,
            "recovery_upload_temp.db"
        )

        with open(temporary_path, "wb") as file:
            file.write(file_bytes)

        connection = sqlite3.connect(temporary_path)

        try:
            result = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if not result or result[0] != "ok":
                raise ValueError("Database integrity check fail hua.")

            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            required_tables = {
                "users",
                "referrals",
                "links",
                "unlocked_links",
                "coin_transactions"
            }

            if not required_tables.issubset(tables):
                raise ValueError(
                    "Backup mein required bot database tables nahi hain."
                )

        finally:
            connection.close()

        with recovery_lock:
            destination = os.path.abspath(DATABASE_FILE)
            source = os.path.abspath(temporary_path)

            if destination == source:
                raise ValueError("Invalid recovery path.")

            os.makedirs(
                os.path.dirname(destination) or ".",
                exist_ok=True
            )

            for extension in ("-wal", "-shm"):
                sidecar = destination + extension

                if os.path.exists(sidecar):
                    os.remove(sidecar)

            os.replace(
                source,
                destination
            )

            temporary_path = None

        bot.send_message(
            chat_id,
            "✅ <b>DATABASE RECOVERED</b>\n\n"
            f"📁 Restored file: <code>{filename}</code>\n\n"
            "Database replace ho gayi hai. "
            "Agar bot database ko memory mein cache karta hai, "
            "to restart ki zaroorat ho sakti hai.",
            parse_mode="HTML"
        )

    except Exception as error:
        bot.send_message(
            chat_id,
            "❌ <b>RECOVERY FAILED</b>\n\n"
            f"<code>{error}</code>",
            parse_mode="HTML"
        )

    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def automatic_backup():
    for admin_id in ADMIN_IDS:
        try:
            backup_path = create_backup()

            with open(backup_path, "rb") as backup_file:
                bot.send_document(
                    admin_id,
                    backup_file,
                    caption=(
                        "🌙 <b>DAILY AUTOMATIC BACKUP</b>\n\n"
                        f"📁 <code>{os.path.basename(backup_path)}</code>\n"
                        "⏰ Scheduled for 12:00 AM IST."
                    ),
                    parse_mode="HTML"
                )

        except Exception as error:
            try:
                bot.send_message(
                    admin_id,
                    f"❌ Automatic backup failed:\n<code>{error}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass


scheduler = BackgroundScheduler(
    timezone=TIMEZONE
)

scheduler.add_job(
    automatic_backup,
    trigger="cron",
    hour=BACKUP_HOUR,
    minute=BACKUP_MINUTE,
    id="daily_database_backup",
    replace_existing=True,
    max_instances=1
)

scheduler.start()
