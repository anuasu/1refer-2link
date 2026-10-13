import sqlite3
from datetime import datetime, timedelta

from config import (
    DATABASE_FILE,
    WELCOME_BONUS,
    REFERRAL_REWARD,
    LINK_UNLOCK_COST,
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def current_time():
    return datetime.now().isoformat(timespec="seconds")


# =========================================================
# DATABASE INITIALIZATION AND SAFE MIGRATIONS
# =========================================================

def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                referred_by INTEGER,
                is_verified INTEGER DEFAULT 0,
                welcome_bonus_claimed INTEGER DEFAULT 0,
                coins_balance INTEGER DEFAULT 0,
                total_coins_earned INTEGER DEFAULT 0,
                total_coins_spent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS referrals (
                referred_user_id INTEGER PRIMARY KEY,
                referrer_id INTEGER NOT NULL,
                rewarded INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                added_by INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unlocked_links (
                user_id INTEGER NOT NULL,
                link_id INTEGER NOT NULL,
                unlocked_at TEXT NOT NULL,
                PRIMARY KEY (user_id, link_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (link_id) REFERENCES links(id)
            );

            CREATE TABLE IF NOT EXISTS coin_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                reward_coins INTEGER NOT NULL,
                max_users INTEGER NOT NULL,
                expires_at TEXT,
                created_by INTEGER,
                is_active INTEGER DEFAULT 1,
                is_auto INTEGER DEFAULT 0,
                channel_id INTEGER,
                message_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS redeem_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                redeemed_at TEXT NOT NULL,
                UNIQUE(code, user_id),
                FOREIGN KEY (code) REFERENCES redeem_codes(code),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS redeem_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                auto_enabled INTEGER DEFAULT 0,
                channel_id INTEGER,
                post_time TEXT DEFAULT '11:00',
                post_date TEXT,
                scheduled_at TEXT,
                repost_interval_hours INTEGER DEFAULT 24,
                reward_coins INTEGER DEFAULT 10,
                max_users INTEGER DEFAULT 100,
                expiry_hours INTEGER DEFAULT 24,
                active_code TEXT,
                active_message_id INTEGER,
                last_post_date TEXT,
                last_delete_date TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_referred_by
                ON users(referred_by);

            CREATE INDEX IF NOT EXISTS idx_users_balance
                ON users(coins_balance DESC);

            CREATE INDEX IF NOT EXISTS idx_links_active
                ON links(is_active);

            CREATE INDEX IF NOT EXISTS idx_transactions_user
                ON coin_transactions(user_id);

            CREATE INDEX IF NOT EXISTS idx_referrals_referrer
                ON referrals(referrer_id);

            CREATE INDEX IF NOT EXISTS idx_redemptions_user
                ON redeem_redemptions(user_id);
        """)

        # Add missing columns to an existing database.
        # Existing tables and records are preserved.
        migrations = {
            "repost_interval_hours":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "repost_interval_hours INTEGER DEFAULT 24",

            "post_date":
                "ALTER TABLE redeem_settings ADD COLUMN post_date TEXT",

            "scheduled_at":
                "ALTER TABLE redeem_settings ADD COLUMN scheduled_at TEXT",

            "active_code":
                "ALTER TABLE redeem_settings ADD COLUMN active_code TEXT",

            "active_message_id":
                "ALTER TABLE redeem_settings ADD COLUMN active_message_id INTEGER",

            "last_post_date":
                "ALTER TABLE redeem_settings ADD COLUMN last_post_date TEXT",

            "last_delete_date":
                "ALTER TABLE redeem_settings ADD COLUMN last_delete_date TEXT",

            "channel_id":
                "ALTER TABLE redeem_settings ADD COLUMN channel_id INTEGER",

            "post_time":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "post_time TEXT DEFAULT '11:00'",

            "reward_coins":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "reward_coins INTEGER DEFAULT 10",

            "max_users":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "max_users INTEGER DEFAULT 100",

            "expiry_hours":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "expiry_hours INTEGER DEFAULT 24",

            "auto_enabled":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "auto_enabled INTEGER DEFAULT 0",

            "updated_at":
                "ALTER TABLE redeem_settings ADD COLUMN "
                "updated_at TEXT",
        }

        settings_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(redeem_settings)"
            ).fetchall()
        }

        for column, sql in migrations.items():
            if column not in settings_columns:
                conn.execute(sql)

        conn.execute("""
            INSERT OR IGNORE INTO redeem_settings (
                id,
                auto_enabled,
                channel_id,
                post_time,
                post_date,
                scheduled_at,
                repost_interval_hours,
                reward_coins,
                max_users,
                expiry_hours,
                updated_at
            )
            VALUES (1, 0, NULL, '11:00', NULL, NULL, 24, 10, 100, 24, ?)
        """, (current_time(),))

        conn.execute("""
            UPDATE redeem_settings
            SET updated_at = ?
            WHERE id = 1 AND updated_at IS NULL
        """, (current_time(),))


# =========================================================
# USER REGISTRATION
# =========================================================

def register_user(
    user_id,
    first_name="",
    username="",
    referred_by=None,
):
    now = current_time()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE users
                SET first_name = ?,
                    username = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (
                first_name or "",
                username or "",
                now,
                user_id,
            ))
            return False

        if referred_by == user_id:
            referred_by = None

        if referred_by is not None:
            referrer = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (referred_by,),
            ).fetchone()

            if not referrer:
                referred_by = None

        conn.execute("""
            INSERT INTO users (
                user_id, first_name, username, referred_by,
                is_verified, welcome_bonus_claimed,
                coins_balance, total_coins_earned,
                total_coins_spent, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
        """, (
            user_id,
            first_name or "",
            username or "",
            referred_by,
            now,
            now,
        ))

        if referred_by is not None:
            conn.execute("""
                INSERT OR IGNORE INTO referrals (
                    referred_user_id, referrer_id, rewarded, created_at
                )
                VALUES (?, ?, 0, ?)
            """, (user_id, referred_by, now))

        return True


def get_user(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def user_exists(user_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone() is not None


def is_user_verified(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_verified FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return bool(row["is_verified"]) if row else False


# =========================================================
# COIN MANAGEMENT
# =========================================================

def add_coins(user_id, amount, transaction_type, description=""):
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount <= 0
    ):
        return False

    now = current_time()

    with get_connection() as conn:
        user = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not user:
            return False

        conn.execute("""
            UPDATE users
            SET coins_balance = coins_balance + ?,
                total_coins_earned = total_coins_earned + ?,
                updated_at = ?
            WHERE user_id = ?
        """, (amount, amount, now, user_id))

        conn.execute("""
            INSERT INTO coin_transactions (
                user_id, amount, transaction_type, description, created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, transaction_type, description, now))

        return True


# =========================================================
# REFERRAL REWARDS
# =========================================================

def reward_pending_referrals(conn, referrer_id, now):
    referrer = conn.execute("""
        SELECT user_id, first_name, username
        FROM users
        WHERE user_id = ? AND is_verified = 1
    """, (referrer_id,)).fetchone()

    if not referrer:
        return []

    pending = conn.execute("""
        SELECT r.referred_user_id, u.first_name, u.username
        FROM referrals r
        JOIN users u ON u.user_id = r.referred_user_id
        WHERE r.referrer_id = ?
          AND r.rewarded = 0
          AND u.is_verified = 1
        ORDER BY r.created_at
    """, (referrer_id,)).fetchall()

    newly_rewarded = []

    for referral in pending:
        referred_user_id = referral["referred_user_id"]

        if referred_user_id == referrer_id:
            continue

        updated = conn.execute("""
            UPDATE referrals
            SET rewarded = 1
            WHERE referred_user_id = ?
              AND referrer_id = ?
              AND rewarded = 0
        """, (referred_user_id, referrer_id))

        if updated.rowcount != 1:
            continue

        conn.execute("""
            UPDATE users
            SET coins_balance = coins_balance + ?,
                total_coins_earned = total_coins_earned + ?,
                updated_at = ?
            WHERE user_id = ?
        """, (REFERRAL_REWARD, REFERRAL_REWARD, now, referrer_id))

        conn.execute("""
            INSERT INTO coin_transactions (
                user_id, amount, transaction_type, description, created_at
            )
            VALUES (?, ?, 'referral_reward', ?, ?)
        """, (
            referrer_id,
            REFERRAL_REWARD,
            f"Successful referral: {referred_user_id}",
            now,
        ))

        balance = conn.execute(
            "SELECT coins_balance FROM users WHERE user_id = ?",
            (referrer_id,),
        ).fetchone()["coins_balance"]

        newly_rewarded.append({
            "referrer_id": referrer_id,
            "referrer_name": referrer["first_name"] or "User",
            "referrer_username": referrer["username"] or "",
            "referrer_balance": balance,
            "referred_user_id": referred_user_id,
            "referred_user_name": referral["first_name"] or "User",
            "referred_user_username": referral["username"] or "",
            "reward": REFERRAL_REWARD,
        })

    return newly_rewarded


def complete_verification(user_id):
    now = current_time()

    result = {
        "success": False,
        "welcome_bonus": 0,
        "referrer_id": None,
        "referrer_name": None,
        "referrer_username": None,
        "newly_rewarded_referrals": [],
        "coins_balance": 0,
    }

    with get_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not user:
            return result

        if not user["is_verified"]:
            conn.execute("""
                UPDATE users
                SET is_verified = 1, updated_at = ?
                WHERE user_id = ?
            """, (now, user_id))

        if not user["welcome_bonus_claimed"]:
            updated = conn.execute("""
                UPDATE users
                SET coins_balance = coins_balance + ?,
                    total_coins_earned = total_coins_earned + ?,
                    welcome_bonus_claimed = 1,
                    updated_at = ?
                WHERE user_id = ?
                  AND welcome_bonus_claimed = 0
            """, (WELCOME_BONUS, WELCOME_BONUS, now, user_id))

            if updated.rowcount == 1:
                conn.execute("""
                    INSERT INTO coin_transactions (
                        user_id, amount, transaction_type,
                        description, created_at
                    )
                    VALUES (?, ?, 'welcome_bonus', 'Welcome bonus', ?)
                """, (user_id, WELCOME_BONUS, now))

                result["welcome_bonus"] = WELCOME_BONUS

        referral = conn.execute("""
            SELECT r.referrer_id, r.rewarded, u.first_name, u.username
            FROM referrals r
            JOIN users u ON u.user_id = r.referrer_id
            WHERE r.referred_user_id = ?
        """, (user_id,)).fetchone()

        if referral:
            result["referrer_id"] = referral["referrer_id"]
            result["referrer_name"] = referral["first_name"] or "User"
            result["referrer_username"] = referral["username"] or ""

            if not referral["rewarded"]:
                result["newly_rewarded_referrals"].extend(
                    reward_pending_referrals(
                        conn, referral["referrer_id"], now
                    )
                )

        result["newly_rewarded_referrals"].extend(
            reward_pending_referrals(conn, user_id, now)
        )

        balance = conn.execute(
            "SELECT coins_balance FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        result["coins_balance"] = balance["coins_balance"]
        result["success"] = True

    return result


# =========================================================
# USER STATISTICS
# =========================================================

def get_user_stats(user_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT coins_balance, total_coins_earned, total_coins_spent
            FROM users WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not row:
            return {
                "coins_balance": 0,
                "total_coins_earned": 0,
                "total_coins_spent": 0,
                "referral_count": 0,
            }

        referral_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM referrals
            WHERE referrer_id = ? AND rewarded = 1
        """, (user_id,)).fetchone()["total"]

        return {
            "coins_balance": row["coins_balance"],
            "total_coins_earned": row["total_coins_earned"],
            "total_coins_spent": row["total_coins_spent"],
            "referral_count": referral_count,
        }


def get_all_user_ids():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users ORDER BY user_id"
        ).fetchall()
        return [row["user_id"] for row in rows]


def get_global_stats():
    with get_connection() as conn:
        total_users = conn.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()["total"]

        total_referrals = conn.execute("""
            SELECT COUNT(*) AS total FROM referrals WHERE rewarded = 1
        """).fetchone()["total"]

        total_coins_spent = conn.execute("""
            SELECT COALESCE(SUM(total_coins_spent), 0) AS total
            FROM users
        """).fetchone()["total"]

        return {
            "total_users": total_users,
            "total_referrals": total_referrals,
            "total_coins_spent": total_coins_spent,
        }


def get_top_users(limit=50):
    limit = max(1, min(int(limit), 50))

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                u.user_id,
                u.first_name,
                u.username,
                u.coins_balance,
                (
                    SELECT COUNT(*)
                    FROM referrals r
                    WHERE r.referrer_id = u.user_id
                      AND r.rewarded = 1
                ) AS referral_count
            FROM users u
            ORDER BY u.coins_balance DESC, u.user_id ASC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


# =========================================================
# REDEEM CODE MANAGEMENT
# =========================================================

def create_redeem_code(
    code,
    reward_coins,
    max_users,
    expires_at=None,
    created_by=None,
    is_auto=False,
    channel_id=None,
    message_id=None,
):
    if not isinstance(code, str):
        return False

    code = code.strip().upper()

    if not code:
        return False

    if (
        not isinstance(reward_coins, int)
        or isinstance(reward_coins, bool)
        or reward_coins <= 0
    ):
        return False

    if (
        not isinstance(max_users, int)
        or isinstance(max_users, bool)
        or max_users <= 0
    ):
        return False

    if isinstance(expires_at, datetime):
        expires_at = expires_at.isoformat(timespec="seconds")

    now = current_time()

    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO redeem_codes (
                    code, reward_coins, max_users, expires_at,
                    created_by, is_active, is_auto, channel_id,
                    message_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (
                code,
                reward_coins,
                max_users,
                expires_at,
                created_by,
                int(bool(is_auto)),
                channel_id,
                message_id,
                now,
            ))
            return True

        except sqlite3.IntegrityError:
            return False


def get_redeem_code(code):
    if not isinstance(code, str):
        return None

    code = code.strip().upper()

    with get_connection() as conn:
        row = conn.execute("""
            SELECT c.*,
                (
                    SELECT COUNT(*)
                    FROM redeem_redemptions r
                    WHERE r.code = c.code
                ) AS redeemed_count
            FROM redeem_codes c
            WHERE c.code = ?
        """, (code,)).fetchone()

        return dict(row) if row else None


def redeem_code_for_user(user_id, code):
    if not isinstance(code, str):
        return {"success": False, "reason": "invalid_code"}

    code = code.strip().upper()

    if not code:
        return {"success": False, "reason": "invalid_code"}

    now = current_time()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            "SELECT user_id, coins_balance FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not user:
            return {"success": False, "reason": "user_not_found"}

        code_row = conn.execute(
            "SELECT * FROM redeem_codes WHERE code = ?",
            (code,),
        ).fetchone()

        if not code_row:
            return {"success": False, "reason": "invalid_code"}

        if not code_row["is_active"]:
            return {"success": False, "reason": "inactive_code"}

        if code_row["expires_at"]:
            try:
                expiry = datetime.fromisoformat(code_row["expires_at"])
                now_dt = (
                    datetime.now(expiry.tzinfo)
                    if expiry.tzinfo
                    else datetime.now()
                )

                if now_dt >= expiry:
                    conn.execute("""
                        UPDATE redeem_codes SET is_active = 0 WHERE code = ?
                    """, (code,))
                    return {"success": False, "reason": "expired_code"}

            except (ValueError, TypeError):
                return {"success": False, "reason": "invalid_expiry"}

        already_redeemed = conn.execute("""
            SELECT 1 FROM redeem_redemptions
            WHERE code = ? AND user_id = ?
        """, (code, user_id)).fetchone()

        if already_redeemed:
            return {"success": False, "reason": "already_redeemed"}

        redeemed_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM redeem_redemptions WHERE code = ?
        """, (code,)).fetchone()["total"]

        if redeemed_count >= code_row["max_users"]:
            conn.execute("""
                UPDATE redeem_codes SET is_active = 0 WHERE code = ?
            """, (code,))
            return {"success": False, "reason": "limit_reached"}

        amount = code_row["reward_coins"]

        conn.execute("""
            INSERT INTO redeem_redemptions (code, user_id, redeemed_at)
            VALUES (?, ?, ?)
        """, (code, user_id, now))

        conn.execute("""
            UPDATE users
            SET coins_balance = coins_balance + ?,
                total_coins_earned = total_coins_earned + ?,
                updated_at = ?
            WHERE user_id = ?
        """, (amount, amount, now, user_id))

        conn.execute("""
            INSERT INTO coin_transactions (
                user_id, amount, transaction_type, description, created_at
            )
            VALUES (?, ?, 'redeem_code', ?, ?)
        """, (user_id, amount, f"Redeemed code: {code}", now))

        return {
            "success": True,
            "code": code,
            "reward_coins": amount,
            "coins_balance": user["coins_balance"] + amount,
            "redeemed_count": redeemed_count + 1,
            "max_users": code_row["max_users"],
        }


def deactivate_redeem_code(code):
    if not isinstance(code, str):
        return False

    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE redeem_codes
            SET is_active = 0
            WHERE code = ? AND is_active = 1
        """, (code.strip().upper(),))

        return cursor.rowcount > 0


def get_redeem_codes(limit=20):
    limit = max(1, min(int(limit), 100))

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*,
                (
                    SELECT COUNT(*)
                    FROM redeem_redemptions r
                    WHERE r.code = c.code
                ) AS redeemed_count
            FROM redeem_codes c
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


# =========================================================
# AUTOMATIC REDEEM SETTINGS
# =========================================================

def get_redeem_settings():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM redeem_settings WHERE id = 1
        """).fetchone()

        return dict(row) if row else None


def update_redeem_settings(**settings):
    allowed = {
        "auto_enabled",
        "channel_id",
        "post_time",
        "post_date",
        "scheduled_at",
        "repost_interval_hours",
        "reward_coins",
        "max_users",
        "expiry_hours",
        "active_code",
        "active_message_id",
        "last_post_date",
        "last_delete_date",
    }

    updates = {
        key: value
        for key, value in settings.items()
        if key in allowed
    }

    if not updates:
        return False

    if "post_time" in updates:
        try:
            datetime.strptime(updates["post_time"], "%H:%M")
        except (ValueError, TypeError):
            return False

    if "post_date" in updates and updates["post_date"] is not None:
        try:
            datetime.strptime(updates["post_date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            return False

    if "scheduled_at" in updates and updates["scheduled_at"] is not None:
        try:
            datetime.fromisoformat(str(updates["scheduled_at"]))
        except (ValueError, TypeError):
            return False

    for key in (
        "reward_coins",
        "max_users",
        "expiry_hours",
        "repost_interval_hours",
    ):
        if key in updates:
            value = updates[key]

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
            ):
                return False

    if "auto_enabled" in updates:
        updates["auto_enabled"] = int(bool(updates["auto_enabled"]))

    for key in ("channel_id", "active_message_id"):
        if key in updates and updates[key] is not None:
            try:
                updates[key] = int(updates[key])
            except (TypeError, ValueError):
                return False

    for key in ("active_code", "active_message_id"):
        if key in updates and updates[key] == "":
            updates[key] = None

    updates["updated_at"] = current_time()

    columns = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values())

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE redeem_settings SET {columns} WHERE id = 1",
            values,
        )
        return cursor.rowcount > 0


def generate_redeem_expiry(hours):
    if (
        not isinstance(hours, int)
        or isinstance(hours, bool)
        or hours <= 0
    ):
        return None

    return (
        datetime.now() + timedelta(hours=hours)
    ).isoformat(timespec="seconds")


# =========================================================
# LINKS MANAGEMENT
# =========================================================

def add_links(urls, admin_id):
    now = current_time()
    added_ids = []

    with get_connection() as conn:
        for url in urls:
            url = url.strip()

            if not url:
                continue

            cursor = conn.execute("""
                INSERT INTO links (url, added_by, is_active, created_at)
                VALUES (?, ?, 1, ?)
            """, (url, admin_id, now))

            added_ids.append(cursor.lastrowid)

    return added_ids


def get_active_links():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, url, added_by, created_at
            FROM links
            WHERE is_active = 1
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_link(link_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM links
            WHERE id = ? AND is_active = 1
        """, (link_id,)).fetchone()

        return dict(row) if row else None


def get_links_count():
    with get_connection() as conn:
        return conn.execute("""
            SELECT COUNT(*) AS total
            FROM links
            WHERE is_active = 1
        """).fetchone()["total"]


def delete_link(link_id):
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE links
            SET is_active = 0
            WHERE id = ? AND is_active = 1
        """, (link_id,))

        return cursor.rowcount > 0


def has_unlocked_link(user_id, link_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT 1 FROM unlocked_links
            WHERE user_id = ? AND link_id = ?
        """, (user_id, link_id)).fetchone()

        return row is not None


def unlock_link(user_id, link_id):
    now = current_time()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute("""
            SELECT coins_balance
            FROM users
            WHERE user_id = ? AND is_verified = 1
        """, (user_id,)).fetchone()

        if not user:
            return {
                "success": False,
                "reason": "user_not_verified",
            }

        link = conn.execute("""
            SELECT id, url FROM links
            WHERE id = ? AND is_active = 1
        """, (link_id,)).fetchone()

        if not link:
            return {
                "success": False,
                "reason": "link_not_found",
            }

        already_unlocked = conn.execute("""
            SELECT 1 FROM unlocked_links
            WHERE user_id = ? AND link_id = ?
        """, (user_id, link_id)).fetchone()

        if already_unlocked:
            return {
                "success": True,
                "already_unlocked": True,
                "url": link["url"],
                "balance": user["coins_balance"],
            }

        updated = conn.execute("""
            UPDATE users
            SET coins_balance = coins_balance - ?,
                total_coins_spent = total_coins_spent + ?,
                updated_at = ?
            WHERE user_id = ?
              AND is_verified = 1
              AND coins_balance >= ?
        """, (
            LINK_UNLOCK_COST,
            LINK_UNLOCK_COST,
            now,
            user_id,
            LINK_UNLOCK_COST,
        ))

        if updated.rowcount != 1:
            return {
                "success": False,
                "reason": "insufficient_coins",
            }

        conn.execute("""
            INSERT INTO unlocked_links (user_id, link_id, unlocked_at)
            VALUES (?, ?, ?)
        """, (user_id, link_id, now))

        conn.execute("""
            INSERT INTO coin_transactions (
                user_id, amount, transaction_type, description, created_at
            )
            VALUES (?, ?, 'link_unlock', ?, ?)
        """, (
            user_id,
            -LINK_UNLOCK_COST,
            f"Unlocked link ID {link_id}",
            now,
        ))

        return {
            "success": True,
            "already_unlocked": False,
            "url": link["url"],
            "balance": user["coins_balance"] - LINK_UNLOCK_COST,
        }


def get_user_unlocked_links(user_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT links.id, links.url, unlocked_links.unlocked_at
            FROM unlocked_links
            JOIN links ON links.id = unlocked_links.link_id
            WHERE unlocked_links.user_id = ?
            ORDER BY unlocked_links.unlocked_at DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]


# =========================================================
# START DATABASE
# =========================================================

init_db()
