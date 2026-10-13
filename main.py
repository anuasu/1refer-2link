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


# =========================================================
# REGISTER HANDLERS
# =========================================================

import handlers.start
import handlers.referral
import handlers.statistics
import handlers.links
import handlers.broadcast
import handlers.backup
import handlers.admin
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
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)

        return parsed.astimezone(LOCAL_TIMEZONE)

    except (TypeError, ValueError, OverflowError):
        logger.exception("Invalid datetime: %r", value)
        return None


def get_initial_scheduled_datetime(settings):
    scheduled_at = settings.get("scheduled_at")

    if scheduled_at:
        return parse_local_datetime(scheduled_at)

    post_time = settings.get("post_time") or "11:00"

    try:
        parsed_time = datetime.strptime(
            post_time,
            "%H:%M",
        ).time()

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
        logger.error("Invalid post_time: %r", post_time)
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
# GET ACTIVE AUTOMATIC CODE
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

def delete_previous_daily_post(settings):
    channel_id = settings.get("channel_id") or CHANNEL_ID
    message_id = settings.get("active_message_id")

    if not channel_id or not message_id:
        logger.error(
            "Missing channel/message ID. "
            "Refusing to delete any message."
        )
        return False

    code_data = get_active_auto_code(settings)

    if not code_data:
        logger.error(
            "Active automatic code not found. "
            "Refusing deletion."
        )
        return False

    code_channel = code_data.get("channel_id")

    if code_channel is not None:
        try:
            if int(code_channel) != int(channel_id):
                logger.error("Channel ID mismatch.")
                return False

        except (TypeError, ValueError):
            logger.error("Invalid channel ID.")
            return False

    try:
        bot.delete_message(
            chat_id=int(channel_id),
            message_id=int(message_id),
        )

    except Exception:
        logger.exception(
            "Failed to delete previous automatic post."
        )
        return False

    saved = update_redeem_settings(
        active_message_id=None,
        active_code=None,
        last_delete_date=get_local_now().date().isoformat(),
    )

    if saved is False:
        logger.error(
            "Old post deleted, but tracking could not be cleared."
        )
        return False

    logger.info(
        "Previous automatic post deleted: %s",
        message_id,
    )

    return True


# =========================================================
# PUBLISH AUTOMATIC REDEEM CODE
# =========================================================

def publish_daily_redeem_code(settings):
    channel_id = settings.get("channel_id") or CHANNEL_ID

    if not channel_id:
        logger.error("CHANNEL_ID is not configured.")
        return False

    try:
        reward = int(settings.get("reward_coins") or 10)
        max_users = int(settings.get("max_users") or 100)
        expiry_hours = int(settings.get("expiry_hours") or 24)

    except (TypeError, ValueError):
        logger.error("Invalid redeem configuration.")
        return False

    if reward <= 0 or max_users <= 0 or expiry_hours <= 0:
        logger.error(
            "Reward, max_users and expiry_hours must be positive."
        )
        return False

    # Generate a unique code.
    code = None

    for _ in range(20):
        candidate = generate_daily_code()

        if not get_redeem_code(candidate):
            code = candidate
            break

    if not code:
        logger.error("Could not generate a unique code.")
        return False

    expires_at = generate_redeem_expiry(expiry_hours)

    if not expires_at:
        logger.error("Could not generate redeem expiry.")
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
        logger.exception("Failed to save automatic redeem code.")
        return False

    if not created:
        logger.error("Automatic redeem code was not saved.")
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
        logger.exception("Failed to publish automatic redeem code.")

        try:
            deactivate_redeem_code(code)
        except Exception:
            logger.exception("Failed to deactivate unpublished code.")

        return False

    # Save the exact message ID for safe deletion later.
    try:
        saved = update_redeem_settings(
            active_code=code,
            active_message_id=sent_message.message_id,
            last_post_date=get_local_now().date().isoformat(),
        )

    except Exception:
        logger.exception("Failed to save automatic-post tracking.")
        saved = False

    if saved is False:
        logger.critical(
            "Code %s was published, but tracking was not saved.",
            code,
        )
        return False

    logger.info("Automatic redeem code published: %s", code)
    return True


# =========================================================
# AUTOMATIC REDEEM SCHEDULER JOB
# =========================================================

def daily_redeem_scheduler_job():
    try:
        settings = get_redeem_settings() or {}

        # Auto redeem OFF.
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
        # FIRST AUTOMATIC POST
        # -------------------------------------------------

        if not active_code and not active_message_id:
            scheduled_at = get_initial_scheduled_datetime(settings)

            if scheduled_at is None:
                logger.error("Initial posting time is invalid.")
                return

            if now < scheduled_at:
                return

            logger.info("Initial automatic posting time reached.")

            publish_daily_redeem_code(settings)
            return

        # -------------------------------------------------
        # CHECK TRACKING
        # -------------------------------------------------

        if not active_code or not active_message_id:
            logger.error(
                "Incomplete automatic-post tracking. "
                "No deletion or replacement will be attempted."
            )
            return

        code_data = get_active_auto_code(settings)

        if not code_data:
            logger.error(
                "Active automatic code is missing or invalid."
            )
            return

        # -------------------------------------------------
        # CHECK REPOST INTERVAL
        # -------------------------------------------------

        created_at = parse_local_datetime(
            code_data.get("created_at")
        )

        if created_at is None:
            logger.error("Could not read code creation time.")
            return

        next_repost_time = created_at + timedelta(
            hours=interval_hours
        )

        if now < next_repost_time:
            return

        logger.info("Repost interval elapsed.")

        # -------------------------------------------------
        # DELETE ONLY TRACKED AUTOMATIC POST
        # -------------------------------------------------

        if not delete_previous_daily_post(settings):
            logger.error(
                "Previous post could not be deleted. "
                "Replacement cancelled."
            )
            return

        # Reload settings before creating another post.
        refreshed_settings = get_redeem_settings() or {}

        if not refreshed_settings.get("auto_enabled", 0):
            logger.info(
                "Automatic redeem was switched OFF."
            )
            return

        if (
            refreshed_settings.get("active_code")
            or refreshed_settings.get("active_message_id")
        ):
            logger.error(
                "Previous post tracking is not cleared. "
                "Replacement cancelled."
            )
            return

        publish_daily_redeem_code(refreshed_settings)

    except Exception:
        logger.exception(
            "Automatic redeem scheduler encountered an error."
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
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)


# =========================================================
# START BOT
# =========================================================

def main():
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


if __name__ == "__main__":
    main()
