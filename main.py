import logging
import secrets
import string

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from bot import bot

from config import CHANNEL_ID, TIMEZONE

from database import (
    get_redeem_settings,
    create_redeem_code,
    get_redeem_code,
    update_redeem_settings,
    generate_redeem_expiry,
    deactivate_redeem_code,
)

# Register handlers
import handlers.start
import handlers.referral
import handlers.statistics
import handlers.links
import handlers.admin
import handlers.broadcast
import handlers.backup
import handlers.redeem


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

LOCAL_TIMEZONE = ZoneInfo(TIMEZONE)


# =========================================================
# TIME HELPERS
# =========================================================

def get_local_now():
    return datetime.now(LOCAL_TIMEZONE)


def parse_local_datetime(value):
    """
    Parse a saved datetime and normalize it to TIMEZONE.

    Naive timestamps from the database are interpreted as
    server-local timestamps for backward compatibility.
    """

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value))

        if parsed.tzinfo is None:
            parsed = parsed.astimezone()

        return parsed.astimezone(LOCAL_TIMEZONE)

    except (TypeError, ValueError, OverflowError):
        logger.exception("Could not parse stored datetime: %r", value)
        return None


def get_initial_scheduled_datetime(settings):
    """
    Prefer the full scheduled_at date/time.

    Older databases may contain only post_time. That fallback
    schedules the next occurrence of the configured clock time.
    """

    scheduled_at = settings.get("scheduled_at")

    if scheduled_at:
        return parse_local_datetime(scheduled_at)

    post_time = settings.get("post_time") or "11:00"

    try:
        parsed_time = datetime.strptime(post_time, "%H:%M").time()
        now = get_local_now()

        scheduled = datetime.combine(
            now.date(),
            parsed_time,
            tzinfo=LOCAL_TIMEZONE,
        )

        if scheduled <= now:
            scheduled += timedelta(days=1)

        return scheduled

    except (TypeError, ValueError):
        logger.error("Invalid configured post_time: %r", post_time)
        return None


# =========================================================
# CODE GENERATOR
# =========================================================

def generate_daily_code(length=12):
    characters = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


# =========================================================
# ACTIVE AUTOMATIC CODE
# =========================================================

def get_active_auto_code(settings):
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
# DELETE TRACKED AUTOMATIC POST ONLY
# =========================================================

def delete_previous_daily_post(settings):
    """
    Delete only the exact message ID saved by the automatic
    posting system. Never delete unrelated channel messages.
    """

    channel_id = settings.get("channel_id") or CHANNEL_ID
    message_id = settings.get("active_message_id")

    if not channel_id or not message_id:
        logger.error("Missing tracked channel/message ID; refusing deletion.")
        return False

    code_data = get_active_auto_code(settings)

    if not code_data:
        logger.error("Active code is missing or not automatic; refusing deletion.")
        return False

    code_channel = code_data.get("channel_id")

    if code_channel is not None:
        try:
            if int(code_channel) != int(channel_id):
                logger.error("Active code channel mismatch; refusing deletion.")
                return False
        except (TypeError, ValueError):
            logger.error("Invalid saved channel ID; refusing deletion.")
            return False

    try:
        bot.delete_message(
            chat_id=int(channel_id),
            message_id=int(message_id),
        )

    except Exception:
        logger.exception(
            "Could not delete the tracked automatic post. "
            "Replacement post will not be published."
        )
        return False

    saved = update_redeem_settings(
        active_message_id=None,
        active_code=None,
        last_delete_date=get_local_now().date().isoformat(),
    )

    if not saved:
        logger.error("Deleted old post, but could not clear tracking in database.")
        return False

    logger.info("Deleted tracked automatic post: %s", message_id)
    return True


# =========================================================
# PUBLISH AUTOMATIC REDEEM CODE
# =========================================================

def publish_daily_redeem_code(settings):
    channel_id = settings.get("channel_id") or CHANNEL_ID

    if not channel_id:
        logger.error("Automatic redeem channel is not configured.")
        return False

    try:
        reward = int(settings.get("reward_coins") or 10)
        max_users = int(settings.get("max_users") or 100)
        expiry_hours = int(settings.get("expiry_hours") or 24)

    except (TypeError, ValueError):
        logger.error("Invalid automatic redeem settings.")
        return False

    if reward <= 0 or max_users <= 0 or expiry_hours <= 0:
        logger.error("Reward, maximum users and expiry must be positive.")
        return False

    # Generate a unique code.
    code = None

    for _ in range(20):
        candidate = generate_daily_code()

        if not get_redeem_code(candidate):
            code = candidate
            break

    if not code:
        logger.error("Could not generate a unique redeem code.")
        return False

    expires_at = generate_redeem_expiry(expiry_hours)

    if not expires_at:
        logger.error("Could not calculate redeem code expiry.")
        return False

    try:
        created = create_redeem_code(
            code=code,
            reward_coins=reward,
            max_users=max_users,
            expires_at=expires_at,
            created_by=0,
            is_auto=True,
            channel_id=channel_id,
        )

    except Exception:
        logger.exception("Could not create automatic redeem code.")
        return False

    if not created:
        logger.error("Could not save automatic redeem code.")
        return False

    message_text = (
        "🎁 <b>AUTOMATIC REDEEM CODE</b>\n\n"
        f"🎟️ Code: <code>{code}</code>\n"
        f"🪙 Reward: <b>{reward} coins</b>\n"
        f"👥 Maximum users: <b>{max_users}</b>\n"
        f"⌛ Code validity: <b>{expiry_hours} hours</b>\n\n"
        "🤖 Open the bot and select Redeem Code.\n"
        "Enter the code to claim your reward.\n\n"
        "⚡ First come, first served!"
    )

    try:
        sent_message = bot.send_message(
            chat_id=int(channel_id),
            text=message_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception:
        logger.exception("Could not publish automatic redeem code.")

        try:
            deactivate_redeem_code(code)
        except Exception:
            logger.exception("Could not deactivate unpublished code.")

        return False

    # Store exact message ID. Without this, safe deletion is impossible.
    saved = update_redeem_settings(
        active_code=code,
        active_message_id=sent_message.message_id,
        last_post_date=get_local_now().date().isoformat(),
    )

    if not saved:
        logger.critical(
            "Code %s was posted, but its message ID was not saved. "
            "Automatic deletion is unsafe until tracking is repaired.",
            code,
        )
        return False

    logger.info("Automatic redeem code published: %s", code)
    return True


# =========================================================
# AUTOMATIC REPOST SCHEDULER
# =========================================================

def daily_redeem_scheduler_job():
    try:
        settings = get_redeem_settings() or {}

        # Auto OFF: do nothing.
        if not settings.get("auto_enabled", 0):
            return

        now = get_local_now()

        try:
            interval_hours = int(
                settings.get("repost_interval_hours") or 24
            )
        except (TypeError, ValueError):
            logger.error("Invalid repost interval.")
            return

        if interval_hours <= 0:
            logger.error("Repost interval must be positive.")
            return

        active_code = settings.get("active_code")
        active_message_id = settings.get("active_message_id")

        # -------------------------------------------------
        # FIRST POST: WAIT FOR THE CONFIGURED DATE AND TIME
        # -------------------------------------------------

        if not active_code and not active_message_id:
            scheduled_at = get_initial_scheduled_datetime(settings)

            if scheduled_at is None:
                logger.error("Initial posting date/time is invalid.")
                return

            # Do not post early.
            if now < scheduled_at:
                return

            logger.info("Initial scheduled time reached.")

            publish_daily_redeem_code(settings)
            return

        # Never guess if tracking is incomplete.
        if not active_code or not active_message_id:
            logger.error(
                "Incomplete automatic-post tracking. "
                "Refusing to delete or publish anything."
            )
            return

        # -------------------------------------------------
        # VERIFY ACTIVE CODE
        # -------------------------------------------------

        code_data = get_active_auto_code(settings)

        if not code_data:
            logger.error(
                "Tracked code is missing or not automatic. "
                "Refusing to delete the tracked post."
            )
            return

        # -------------------------------------------------
        # CHECK REPOST INTERVAL
        # -------------------------------------------------

        created_at = parse_local_datetime(code_data.get("created_at"))

        if created_at is None:
            logger.error("Could not parse active code creation time.")
            return

        next_repost_time = created_at + timedelta(hours=interval_hours)

        if now < next_repost_time:
            return

        logger.info("Repost interval elapsed; replacing tracked post.")

        # -------------------------------------------------
        # DELETE ONLY THE TRACKED AUTOMATIC POST
        # -------------------------------------------------

        if not delete_previous_daily_post(settings):
            logger.error("Old post deletion failed; skipping replacement.")
            return

        # Re-read settings in case Auto was switched OFF.
        refreshed_settings = get_redeem_settings() or {}

        if not refreshed_settings.get("auto_enabled", 0):
            logger.info("Auto Redeem is OFF; not publishing replacement.")
            return

        # Ensure tracking was cleared before publishing.
        if (
            refreshed_settings.get("active_code")
            or refreshed_settings.get("active_message_id")
        ):
            logger.error("Tracking was not cleared; refusing to publish.")
            return

        publish_daily_redeem_code(refreshed_settings)

    except Exception:
        logger.exception("Automatic redeem scheduler failed.")


# =========================================================
# SCHEDULER
# =========================================================

scheduler = BackgroundScheduler(timezone=LOCAL_TIMEZONE)

scheduler.add_job(
    daily_redeem_scheduler_job,
    trigger="interval",
    minutes=1,
    id="daily_redeem_code_scheduler",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
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
        logger.info("Bot stopped by user.")

    except Exception:
        logger.exception("Bot stopped unexpectedly.")

    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)

        logger.info("Scheduler stopped.")
