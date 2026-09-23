import sqlite3

from config import DB_NAME


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT NOT NULL
        )
    """)

    columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(user_keys)"
        ).fetchall()
    }

    if "api_url" not in columns:
        cursor.execute(
            "ALTER TABLE user_keys ADD COLUMN api_url TEXT"
        )

    if "model" not in columns:
        cursor.execute(
            "ALTER TABLE user_keys ADD COLUMN model TEXT"
        )

    conn.commit()
    conn.close()


def save_api_config(
    user_id,
    api_url,
    api_key,
    model=None
):
    conn = get_connection()

    conn.execute("""
        INSERT INTO user_keys (
            user_id,
            api_key,
            api_url,
            model
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            api_key = excluded.api_key,
            api_url = excluded.api_url,
            model = excluded.model
    """, (
        user_id,
        api_key,
        api_url,
        model
    ))

    conn.commit()
    conn.close()


def save_model(user_id, model):
    conn = get_connection()

    conn.execute(
        """
        UPDATE user_keys
        SET model = ?
        WHERE user_id = ?
        """,
        (
            model,
            user_id
        )
    )

    conn.commit()
    conn.close()


def get_api_config(user_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            user_id,
            api_key,
            api_url,
            model
        FROM user_keys
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not row:
        return None

    return dict(row)