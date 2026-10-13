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

# Import handlers so their message/callback handlers register
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
# CODE GENERATOR
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
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
        else:
            parsed = parsed.astimezone(LOCAL_TIMEZONE)

        return parsed

    except (TypeError, ValueError):
        logger.exception("Could not parse stored datetime")
        return None


# =========================================================
# VERIFY ACTIVE AUTOMATIC CODE
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
# DELETE PREVIOUS AUTOMATIC POST
# =========================================================

def delete_previous_daily_post(settings, today=None):
    """
    Deletes only the message ID saved for the active automatic code.
    Never searches for or deletes unrelated/manual channel messages.
    """

    channel_id = settings.get("channel_id") or CHANNEL_ID
    message_id = settings.get("active_message_id")

    if not message_id:
        logger.warning(
            "No tracked automatic message ID. "
            "Refusing to delete any channel message."
        )
        return False

    code_data = get_active_auto_code(settings)

    if not code_data:
        logger.error(
            "Active code is missing or is not automatic. "
            "Refusing to delete the message."
        )
        return False

    code_channel = code_data.get("channel_id")

    if code_channel is not None:
        try:
            if int(code_channel) != int(channel_id):
                logger.error(
                    "Channel mismatch. Refusing to delete the message."
                )
                return False
        except (TypeError, ValueError):
            logger.error("Invalid channel ID for active redeem code")
            return False

    try:
        bot.delete_message(
            chat_id=channel_id,
            message_id=int(message_id),
        )

        logger.info(
            "Previous automatic redeem post deleted: %s",
            message_id,
        )

        saved = update_redeem_settings(
            active_message_id=None,
            last_delete_date=(
                today or get_local_now().date().isoformat()
            ),
        )

        if not saved:
            logger.error(
                "Deleted old post, but could not update database settings."
            )
            return False

        return True

    except Exception:
        logger.exception(
            "Could not delete the previous automatic redeem post"
        )
        return False


# =========================================================
# PUBLISH NEW AUTOMATIC REDEEM CODE
# =========================================================

def publish_daily_redeem_code(settings, today=None):
    channel_id = settings.get("channel_id") or CHANNEL_ID

    try:
        reward = int(settings.get("reward_coins") or 10)
        max_users = int(settings.get("max_users") or 100)
        expiry_hours = int(settings.get("expiry_hours") or 24)
    except (TypeError, ValueError):
        logger.error("Invalid automatic redeem settings")
        return False

    if reward <= 0 or max_users <= 0 or expiry_hours <= 0:
        logger.error("Reward, maximum users and expiry must be positive")
        return False

    # Generate a code that does not already exist.
    code = None

    for _ in range(10):
        candidate = generate_daily_code()

        if not get_redeem_code(candidate):
            code = candidate
            break

    if not code:
        logger.error("Could not generate a unique redeem code")
        return False

    expires_at = generate_redeem_expiry(expiry_hours)

    if not expires_at:
        logger.error("Could not generate redeem expiry")
        return False

    created = create_redeem_code(
        code=code,
        reward_coins=reward,
        max_users=max_users,
        expires_at=expires_at,
        created_by=0,
        is_auto=True,
        channel_id=channel_id,
    )

    if not created:
        logger.error("Could not save automatic redeem code")
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
            chat_id=channel_id,
            text=message_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception:
        logger.exception("Failed to publish automatic redeem code")

        try:
            deactivate_redeem_code(code)
        except Exception:
            logger.exception("Could not deactivate unpublished redeem code")

        return False

    now = get_local_now()

    saved = update_redeem_settings(
        active_code=code,
        active_message_id=sent_message.message_id,
        last_post_date=now.date().isoformat(),
    )

    if not saved:
        logger.error(
            "Code was posted, but its message ID could not be saved. "
            "Do not enable another automatic post until this is checked."
        )
        return False

    logger.info(
        "Automatic redeem code published successfully: %s",
        code,
    )

    return True


# =========================================================
# AUTOMATIC REPOST SCHEDULER
# =========================================================

def daily_redeem_scheduler_job():
    try:
        settings = get_redeem_settings() or {}

        # Auto OFF means do nothing.
        if not settings.get("auto_enabled", 0):
            return

        now = get_local_now()
        today = now.date().isoformat()

        try:
            interval_hours = int(
                settings.get("repost_interval_hours") or 24
            )
        except (TypeError, ValueError):
            logger.error("Invalid automatic repost interval")
            return

        if interval_hours <= 0:
            logger.error("Repost interval must be positive")
            return

        active_code = settings.get("active_code")
        active_message_id = settings.get("active_message_id")

        # -------------------------------------------------
        # No currently tracked automatic post
        # -------------------------------------------------

        if not active_code and not active_message_id:
            post_time = settings.get("post_time") or "11:00"

            try:
                target_time = datetime.strptime(
                    post_time,
                    "%H:%M",
                ).time()
            except ValueError:
                logger.error("Invalid initial post time: %s", post_time)
                return

            current_time = now.time().replace(
                second=0,
                microsecond=0,
            )

            if current_time != target_time:
                return

            logger.info("Publishing initial automatic redeem post")

            publish_daily_redeem_code(settings, today)
            return

        # If only one of the tracking fields exists, don't guess.
        if not active_code or not active_message_id:
            logger.error(
                "Incomplete automatic post tracking data. "
                "No message will be deleted or published."
            )
            return

        # -------------------------------------------------
        # Validate the active code
        # -------------------------------------------------

        code_data = get_active_auto_code(settings)

        if not code_data:
            logger.error(
                "Tracked code is missing or is not automatic. "
                "Refusing to delete the tracked message."
            )
            return

        # -------------------------------------------------
        # Check when the current code was created
        # -------------------------------------------------

        created_at = parse_local_datetime(
            code_data.get("created_at")
        )

        if created_at is None:
            logger.error(
                "Could not determine active code creation time"
            )
            return

        next_repost_time = created_at + timedelta(
            hours=interval_hours
        )

        if now < next_repost_time:
            return

        logger.info(
            "Repost interval elapsed. Replacing automatic redeem post."
        )

        # -------------------------------------------------
        # Delete the old tracked post
        # -------------------------------------------------

        if not delete_previous_daily_post(settings, today):
            logger.warning(
                "Old post deletion failed. New code will not be posted."
            )
            return

        # -------------------------------------------------
        # Refresh settings and publish the next code
        # -------------------------------------------------

        refreshed_settings = get_redeem_settings() or {}

        if not refreshed_settings.get("auto_enabled", 0):
            logger.info("Auto Redeem is OFF; skipping next post")
            return

        # Clear the previous active code reference before publishing.
        # Keep the old code record in the database for redemption history.
        if not update_redeem_settings(active_code=None):
            logger.error(
                "Could not clear previous active code reference"
            )
            return

        refreshed_settings = get_redeem_settings() or {}

        publish_daily_redeem_code(
            refreshed_settings,
            today,
        )

    except Exception:
        logger.exception("Automatic redeem scheduler failed")


# =========================================================
# SCHEDULER
# =========================================================

scheduler = BackgroundScheduler(
    timezone=LOCAL_TIMEZONE,
)

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
        logger.info("Bot stopped by user")

    except Exception:
        logger.exception("Bot stopped unexpectedly")

    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)

        logger.info("Scheduler stopped")
