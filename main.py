import logging
import secrets
import string

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from apscheduler.schedulers.background import BackgroundScheduler

from config import (
    BOT_TOKEN,
    CHANNEL_ID,
    TIMEZONE,
)

from database import (
    get_redeem_settings,
    create_redeem_code,
    get_redeem_code,
    update_redeem_settings,
    generate_redeem_expiry,
)

# =========================================================
# HANDLERS
# =========================================================

from handlers import start
from handlers import referral
from handlers import statistics
from handlers import links
from handlers import admin
from handlers import broadcast
from handlers import backup
from handlers import redeem


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# =========================================================
# BOT
# =========================================================

bot = telebot.TeleBot(BOT_TOKEN)

LOCAL_TIMEZONE = ZoneInfo(TIMEZONE)


# =========================================================
# REDEEM CODE GENERATOR
# =========================================================

def generate_daily_code(length=12):
    characters = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


# =========================================================
# TIME HELPERS
# =========================================================

def get_local_now():
    return datetime.now(LOCAL_TIMEZONE)


def parse_local_datetime(value):
    """
    Parse a stored datetime and make it comparable
    with the configured local timezone.
    """
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
        else:
            parsed = parsed.astimezone(LOCAL_TIMEZONE)

        return parsed

    except (ValueError, TypeError):
        logger.exception("Could not parse stored datetime")
        return None


def get_active_auto_code(settings):
    """
    Only return the code if the saved active code is
    actually an automatic code.
    """
    active_code = settings.get("active_code")

    if not active_code:
        return None

    code_data = get_redeem_code(active_code)

    if not code_data:
        return None

    if not code_data.get("is_auto"):
        return None

    return code_data


# =========================================================
# DELETE PREVIOUS AUTOMATIC POST
# =========================================================

def delete_previous_daily_post(settings, today=None):
    """
    Delete only the currently tracked automatic post.

    Manual redeem posts are never selected by this function.
    If deletion fails, return False so a new post is not sent.
    """

    channel_id = (
        settings.get("channel_id")
        or CHANNEL_ID
    )

    message_id = settings.get("active_message_id")
    active_code = settings.get("active_code")

    if not message_id:
        logger.warning(
            "No tracked automatic message ID found. "
            "Will not delete any message."
        )

        return False

    # Safety check: the active code must be an automatic code.
    code_data = get_active_auto_code(settings)

    if not code_data:
        logger.warning(
            "Active code is missing or is not an automatic code. "
            "Refusing to delete the tracked message."
        )

        return False

    # Do not delete a message from a different channel.
    code_channel = code_data.get("channel_id")

    if code_channel is not None:
        try:
            if int(code_channel) != int(channel_id):
                logger.error(
                    "Channel mismatch detected. "
                    "Refusing to delete the message."
                )
                return False
        except (TypeError, ValueError):
            logger.error("Invalid channel ID in active redeem code")
            return False

    try:
        bot.delete_message(
            chat_id=channel_id,
            message_id=int(message_id),
        )

        logger.info(
            "Deleted previous automatic redeem post: %s",
            message_id,
        )

        update_redeem_settings(
            active_message_id=None,
            last_delete_date=(
                today
                or get_local_now().date().isoformat()
            ),
        )

        return True

    except Exception:
        logger.exception(
            "Failed to delete previous automatic redeem post"
        )

        return False


# =========================================================
# PUBLISH NEW AUTOMATIC REDEEM CODE
# =========================================================

def publish_daily_redeem_code(settings, today=None):
    """
    Generate a new automatic redeem code and post it
    to the configured channel.
    """

    channel_id = (
        settings.get("channel_id")
        or CHANNEL_ID
    )

    try:
        reward_coins = int(
            settings.get("reward_coins") or 10
        )

        max_users = int(
            settings.get("max_users") or 100
        )

        expiry_hours = int(
            settings.get("expiry_hours") or 24
        )

    except (TypeError, ValueError):
        logger.error("Invalid automatic redeem settings")
        return False

    if (
        reward_coins <= 0
        or max_users <= 0
        or expiry_hours <= 0
    ):
        logger.error("Redeem settings must be positive")
        return False

    expiry_time = generate_redeem_expiry(expiry_hours)

    if not expiry_time:
        logger.error("Could not generate redeem expiry")
        return False

    # Generate a unique code.
    code = None

    for _ in range(10):
        candidate = generate_daily_code()

        existing = get_redeem_code(candidate)

        if not existing:
            code = candidate
            break

    if not code:
        logger.error("Could not generate a unique redeem code")
        return False

    created = create_redeem_code(
        code=code,
        reward_coins=reward_coins,
        max_users=max_users,
        expires_at=expiry_time,
        created_by=None,
        is_auto=True,
        channel_id=channel_id,
    )

    if not created:
        logger.error("Failed to save automatic redeem code")
        return False

    expiry_display = expiry_time.replace("T", " ")

    message_text = (
        "🎁 <b>DAILY REDEEM CODE</b>\n\n"
        f"🎟️ <b>Code:</b> <code>{code}</code>\n"
        f"🪙 <b>Reward:</b> {reward_coins} coins\n"
        f"👥 <b>Maximum Users:</b> {max_users}\n"
        f"⏳ <b>Expires:</b> {expiry_display}\n\n"
        "📌 Redeem the code before it expires.\n"
        "⚠️ Each user can redeem this code only once."
    )

    try:
        sent_message = bot.send_message(
            chat_id=channel_id,
            text=message_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception:
        logger.exception(
            "Could not publish automatic redeem code"
        )

        # Deactivate the unused code because the post failed.
        from database import deactivate_redeem_code

        deactivate_redeem_code(code)

        return False

    # Save the message ID only after Telegram confirms posting.
    now = get_local_now()

    updated = update_redeem_settings(
        active_code=code,
        active_message_id=sent_message.message_id,
        last_post_date=now.date().isoformat(),
    )

    if not updated:
        logger.error(
            "Message was posted, but settings could not be saved. "
            "Check the database before enabling another post."
        )

        return False

    logger.info(
        "Automatic redeem code published: %s",
        code,
    )

    return True


# =========================================================
# AUTOMATIC REDEEM SCHEDULER
# =========================================================

def daily_redeem_scheduler_job():
    """
    Runs every minute.

    Behaviour:
    1. If Auto is OFF, do nothing.
    2. If there is no active automatic post, wait for post_time.
    3. If an automatic post exists, wait until the configured
       repost interval has elapsed.
    4. Delete only the tracked automatic post.
    5. Publish a new code after successful deletion.
    """

    try:
        settings = get_redeem_settings()

        if not settings:
            logger.warning("Redeem settings were not found")
            return

        if not settings.get("auto_enabled"):
            return

        now = get_local_now()
        today = now.date().isoformat()

        try:
            interval_hours = int(
                settings.get("repost_interval_hours") or 24
            )
        except (TypeError, ValueError):
            logger.error("Invalid repost interval")
            return

        if interval_hours <= 0:
            logger.error("Repost interval must be greater than zero")
            return

        # -------------------------------------------------
        # CASE 1: No tracked automatic post currently exists
        # -------------------------------------------------

        active_message_id = settings.get("active_message_id")
        active_code = settings.get("active_code")

        if not active_message_id or not active_code:
            post_time = settings.get("post_time") or "11:00"

            try:
                scheduled_time = datetime.strptime(
                    post_time,
                    "%H:%M",
                ).time()
            except ValueError:
                logger.error("Invalid initial post time: %s", post_time)
                return

            current_time_only = now.time().replace(
                second=0,
                microsecond=0,
            )

            if current_time_only != scheduled_time:
                return

            logger.info(
                "No active automatic post. "
                "Publishing the initial code at %s",
                post_time,
            )

            publish_daily_redeem_code(
                settings,
                today,
            )

            return

        # -------------------------------------------------
        # CASE 2: Verify the tracked post is automatic
        # -------------------------------------------------

        code_data = get_active_auto_code(settings)

        if not code_data:
            logger.error(
                "Tracked code is missing or not automatic. "
                "Refusing to delete any message."
            )
            return

        # -------------------------------------------------
        # CASE 3: Calculate when the next repost is due
        # -------------------------------------------------

        last_post_at = parse_local_datetime(
            code_data.get("created_at")
        )

        if last_post_at is None:
            logger.error(
                "Cannot determine the active code creation time. "
                "Skipping repost to avoid deleting the wrong post."
            )
            return

        next_post_at = last_post_at + timedelta(
            hours=interval_hours
        )

        if now < next_post_at:
            return

        logger.info(
            "Automatic redeem repost is due. "
            "Interval: %s hours",
            interval_hours,
        )

        # -------------------------------------------------
        # CASE 4: Delete the previous automatic post
        # -------------------------------------------------

        deleted = delete_previous_daily_post(
            settings,
            today,
        )

        if not deleted:
            logger.warning(
                "Old automatic post could not be deleted. "
                "New post will not be published yet."
            )
            return

        # -------------------------------------------------
        # CASE 5: Publish the next code
        # -------------------------------------------------

        # Refresh settings after deletion.
        refreshed_settings = get_redeem_settings()

        if not refreshed_settings:
            logger.error(
                "Could not reload redeem settings after deletion"
            )
            return

        if not refreshed_settings.get("auto_enabled"):
            logger.info(
                "Auto was switched OFF before publishing the next code"
            )
            return

        publish_daily_redeem_code(
            refreshed_settings,
            today,
        )

    except Exception:
        logger.exception(
            "Unexpected error in automatic redeem scheduler"
        )


# =========================================================
# SCHEDULER SETUP
# =========================================================

scheduler = BackgroundScheduler(
    timezone=LOCAL_TIMEZONE,
)

scheduler.add_job(
    daily_redeem_scheduler_job,
    trigger="interval",
    minutes=1,
    id="daily_redeem_code_scheduler",
    max_instances=1,
    coalesce=True,
    replace_existing=True,
)


# =========================================================
# START BOT
# =========================================================

if __name__ == "__main__":
    try:
        scheduler.start()

        logger.info(
            "Automatic redeem scheduler started. Timezone: %s",
            TIMEZONE,
        )

        logger.info("Bot is starting...")

        bot.infinity_polling(
            skip_pending=True,
            timeout=30,
            long_polling_timeout=30,
        )

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

    except Exception:
        logger.exception("Bot stopped because of an unexpected error")

    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)

        logger.info("Scheduler stopped")
