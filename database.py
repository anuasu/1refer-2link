import sqlite3
from datetime import datetime
from config import DATABASE_FILE, WELCOME_BONUS, REFERRAL_REWARD, LINK_UNLOCK_COST


def get_connection():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def current_time():
    return datetime.now().isoformat(timespec="seconds")


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

            CREATE INDEX IF NOT EXISTS idx_users_referred_by
            ON users(referred_by);

            CREATE INDEX IF NOT EXISTS idx_links_active
            ON links(is_active);

            CREATE INDEX IF NOT EXISTS idx_transactions_user
            ON coin_transactions(user_id);
        """)


def register_user(user_id, first_name="", username="", referred_by=None):
    now = current_time()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE users
                SET first_name = ?, username = ?, updated_at = ?
                WHERE user_id = ?
            """, (first_name or "", username or "", now, user_id))

            return False

        if referred_by == user_id:
            referred_by = None

        if referred_by is not None:
            referrer = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (referred_by,)
            ).fetchone()

            if not referrer:
                referred_by = None

        conn.execute("""
            INSERT INTO users (
                user_id, first_name, username, referred_by,
                is_verified, welcome_bonus_claimed, coins_balance,
                total_coins_earned, total_coins_spent,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
        """, (
            user_id,
            first_name or "",
            username or "",
            referred_by,
            now,
            now
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
            (user_id,)
        ).fetchone()

        return dict(row) if row else None


def user_exists(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        return row is not None


def is_user_verified(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_verified FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        return bool(row["is_verified"]) if row else False


def add_coins(user_id, amount, transaction_type, description=""):
    if amount <= 0:
        return False

    now = current_time()

    with get_connection() as conn:
        user = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
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


def complete_verification(user_id):
    now = current_time()
    result = {
        "success": False,
        "welcome_bonus": 0,
        "referral_reward": 0,
        "referrer_id": None
    }

    with get_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not user:
            return result

        if user["is_verified"]:
            result["success"] = True
            return result

        conn.execute("""
            UPDATE users
            SET is_verified = 1, updated_at = ?
            WHERE user_id = ?
        """, (now, user_id))

        if not user["welcome_bonus_claimed"]:
            conn.execute("""
                UPDATE users
                SET coins_balance = coins_balance + ?,
                    total_coins_earned = total_coins_earned + ?,
                    welcome_bonus_claimed = 1,
                    updated_at = ?
                WHERE user_id = ?
            """, (WELCOME_BONUS, WELCOME_BONUS, now, user_id))

            conn.execute("""
                INSERT INTO coin_transactions (
                    user_id, amount, transaction_type, description, created_at
                )
                VALUES (?, ?, 'welcome_bonus', 'Welcome bonus', ?)
            """, (user_id, WELCOME_BONUS, now))

            result["welcome_bonus"] = WELCOME_BONUS

        referral = conn.execute("""
            SELECT referrer_id, rewarded
            FROM referrals
            WHERE referred_user_id = ?
        """, (user_id,)).fetchone()

        if referral and not referral["rewarded"]:
            referrer_id = referral["referrer_id"]

            if referrer_id != user_id:
                referrer = conn.execute("""
                    SELECT user_id, is_verified
                    FROM users
                    WHERE user_id = ?
                """, (referrer_id,)).fetchone()

                if referrer and referrer["is_verified"]:
                    conn.execute("""
                        UPDATE users
                        SET coins_balance = coins_balance + ?,
                            total_coins_earned = total_coins_earned + ?,
                            updated_at = ?
                        WHERE user_id = ?
                    """, (
                        REFERRAL_REWARD,
                        REFERRAL_REWARD,
                        now,
                        referrer_id
                    ))

                    conn.execute("""
                        INSERT INTO coin_transactions (
                            user_id, amount, transaction_type,
                            description, created_at
                        )
                        VALUES (?, ?, 'referral_reward', ?, ?)
                    """, (
                        referrer_id,
                        REFERRAL_REWARD,
                        f"Successful referral: {user_id}",
                        now
                    ))

                    conn.execute("""
                        UPDATE referrals
                        SET rewarded = 1
                        WHERE referred_user_id = ?
                    """, (user_id,))

                    result["referral_reward"] = REFERRAL_REWARD
                    result["referrer_id"] = referrer_id

        result["success"] = True
        return result


def get_user_stats(user_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                coins_balance,
                total_coins_earned,
                total_coins_spent
            FROM users
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not row:
            return {
                "coins_balance": 0,
                "total_coins_earned": 0,
                "total_coins_spent": 0,
                "referral_count": 0
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
            "referral_count": referral_count
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

        total_referrals = conn.execute(
            "SELECT COUNT(*) AS total FROM referrals WHERE rewarded = 1"
        ).fetchone()["total"]

        total_coins_spent = conn.execute(
            "SELECT COALESCE(SUM(total_coins_spent), 0) AS total FROM users"
        ).fetchone()["total"]

        return {
            "total_users": total_users,
            "total_referrals": total_referrals,
            "total_coins_spent": total_coins_spent
        }


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
            SELECT *
            FROM links
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
            SELECT 1
            FROM unlocked_links
            WHERE user_id = ? AND link_id = ?
        """, (user_id, link_id)).fetchone()

        return row is not None


def unlock_link(user_id, link_id):
    now = current_time()

    with get_connection() as conn:
        user = conn.execute("""
            SELECT coins_balance
            FROM users
            WHERE user_id = ? AND is_verified = 1
        """, (user_id,)).fetchone()

        if not user:
            return {
                "success": False,
                "reason": "user_not_verified"
            }

        link = conn.execute("""
            SELECT id, url
            FROM links
            WHERE id = ? AND is_active = 1
        """, (link_id,)).fetchone()

        if not link:
            return {
                "success": False,
                "reason": "link_not_found"
            }

        already_unlocked = conn.execute("""
            SELECT 1
            FROM unlocked_links
            WHERE user_id = ? AND link_id = ?
        """, (user_id, link_id)).fetchone()

        if already_unlocked:
            return {
                "success": True,
                "already_unlocked": True,
                "url": link["url"],
                "balance": user["coins_balance"]
            }

        if user["coins_balance"] < LINK_UNLOCK_COST:
            return {
                "success": False,
                "reason": "insufficient_coins",
                "balance": user["coins_balance"]
            }

        conn.execute("""
            UPDATE users
            SET coins_balance = coins_balance - ?,
                total_coins_spent = total_coins_spent + ?,
                updated_at = ?
            WHERE user_id = ?
        """, (LINK_UNLOCK_COST, LINK_UNLOCK_COST, now, user_id))

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
            now
        ))

        new_balance = user["coins_balance"] - LINK_UNLOCK_COST

        return {
            "success": True,
            "already_unlocked": False,
            "url": link["url"],
            "balance": new_balance
        }


def get_user_unlocked_links(user_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                links.id,
                links.url,
                unlocked_links.unlocked_at
            FROM unlocked_links
            JOIN links ON links.id = unlocked_links.link_id
            WHERE unlocked_links.user_id = ?
            ORDER BY unlocked_links.unlocked_at DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]


init_db()
