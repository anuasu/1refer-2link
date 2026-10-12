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
)

# ==========================================
# REGISTER EXISTING HANDLERS
# ==========================================

import handlers.start
import handlers.referral
import handlers.statistics
import handlers.links
import handlers.admin
import handlers.broadcast
import handlers.backup
import handlers.redeem


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

LOCAL_TIMEZONE = ZoneInfo(TIMEZONE)


# ==========================================
# RANDOM REDEEM CODE
# ==========================================

def generate_daily_code(length=12):
    characters = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


# ==========================================
# DELETE PREVIOUS DAILY POST
# ==========================================

def delete_previous_daily_post(settings, today):
    message_id = settings.get("active_message_id")
    channel_id = settings.get("channel_id") or CHANNEL_ID

    if not message_id:
        logger.info("No previous daily redeem post to delete.")

        update_redeem_settings(
            last_delete_date=today
        )
        return True

    try:
        bot.delete_message(
            chat_id=channel_id,
            message_id=int(message_id),
        )

        logger.info("Previous daily redeem post deleted.")

        update_redeem_settings(
            last_delete_date=today
        )

        return True

    except Exception:
        logger.exception(
            "Could not delete previous daily redeem post. "
            "Will retry during the next scheduler check."
        )

        # Do not update last_delete_date on failure.
        # This allows another attempt on the next check.
        return False


# ==========================================
# CREATE AND POST DAILY REDEEM CODE
# ==========================================

def publish_daily_redeem_code(settings, today):
    channel_id = settings.get("channel_id") or CHANNEL_ID

    reward = int(settings.get("reward_coins", 10))
    max_users = int(settings.get("max_users", 100))
    expiry_hours = int(settings.get("expiry_hours", 24))

    if reward <= 0 or max_users <= 0 or expiry_hours <= 0:
        logger.error(
            "Invalid daily redeem settings: reward=%s, "
            "max_users=%s, expiry_hours=%s",
            reward,
            max_users,
            expiry_hours,
        )
        return False

    code = generate_daily_code()

    try:
        expires_at = generate_redeem_expiry(expiry_hours)

        if not expires_at:
            logger.error("Could not generate redeem code expiry.")
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
            logger.error("Daily redeem code creation failed.")
            return False

        code_data = get_redeem_code(code)

        if not code_data:
            logger.error(
                "Created daily redeem code could not be retrieved."
            )
            return False

        post_text = (
            "🎁 <b>DAILY REDEEM CODE</b>\n\n"
            f"🎟 Code: <code>{code}</code>\n"
            f"🪙 Reward: <b>{reward} coins</b>\n"
            f"👥 Limited to <b>{max_users} users</b>\n\n"
            "🤖 Open the bot and select 🎁 Redeem Code.\n"
            "Enter the code to claim your reward.\n\n"
            "⚡ First come, first served!"
        )

        sent_message = bot.send_message(
            chat_id=channel_id,
            text=post_text,
            parse_mode="HTML",
        )

        # Save active post details only after successful posting.
        saved = update_redeem_settings(
            active_code=code,
            active_message_id=sent_message.message_id,
            last_post_date=today,
        )

        if not saved:
            logger.error(
                "Post was published, but scheduler settings "
                "could not be updated. Message ID: %s",
                sent_message.message_id,
            )
            return False

        logger.info(
            "Daily redeem code published successfully: %s",
            code,
        )

        return True

    except Exception:
        logger.exception(
            "Failed to create or publish daily redeem code."
        )
        return False


# ==========================================
# DAILY SCHEDULER CHECK
# ==========================================

def daily_redeem_scheduler_job():
    """
    Runs every minute.

    Deletes the previous daily post one minute before
    the configured posting time, then publishes the
    next code at the configured time.
    """

    try:
        now = datetime.now(LOCAL_TIMEZONE)

        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        settings = get_redeem_settings() or {}

        if not settings.get("auto_enabled", 0):
            return

        post_time = settings.get("post_time", "11:00")

        try:
            parsed_time = datetime.strptime(
                post_time,
                "%H:%M",
            )
        except (TypeError, ValueError):
            logger.error(
                "Invalid automatic redeem posting time: %s",
                post_time,
            )
            return

        scheduled_hour = parsed_time.hour
        scheduled_minute = parsed_time.minute

        scheduled_datetime = datetime(
            2000,
            1,
            1,
            scheduled_hour,
            scheduled_minute,
        )

        delete_time = (
            scheduled_datetime - timedelta(minutes=1)
        ).strftime("%H:%M")

        # Delete the previous post one minute before
        # the next scheduled post.
        if current_time == delete_time:
            if settings.get("last_delete_date") != today:
                delete_previous_daily_post(
                    settings,
                    today,
                )

        # Publish the new code at the configured time.
        if current_time == post_time:
            settings = get_redeem_settings() or {}

            if settings.get("last_post_date") == today:
                return

            publish_daily_redeem_code(
                settings,
                today,
            )

    except Exception:
        logger.exception(
            "Daily redeem scheduler encountered an error."
        )


# ==========================================
# START SCHEDULER
# ==========================================

scheduler = BackgroundScheduler(
    timezone=LOCAL_TIMEZONE,
)

scheduler.add_job(
    daily_redeem_scheduler_job,
    trigger="cron",
    second=5,
    id="daily_redeem_code_scheduler",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)


# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    print("🤖 Bot is starting...")

    try:
        scheduler.start()

        print("⏰ Daily redeem scheduler started.")
        print(f"🌏 Timezone: {TIMEZONE}")

        bot.infinity_polling(
            skip_pending=True,
            timeout=30,
            long_polling_timeout=30,
        )

    except KeyboardInterrupt:
        print("Bot stopped.")

    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
