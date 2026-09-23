import sqlite3
from config import DB_FILE

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_api_key(user_id: int, api_key: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO api_keys (user_id, api_key) 
        VALUES (?, ?) 
        ON CONFLICT(user_id) 
        DO UPDATE SET api_key=excluded.api_key
    """, (user_id, api_key))
    conn.commit()
    conn.close()

def get_api_key(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM api_keys WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
