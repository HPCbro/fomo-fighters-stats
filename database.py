# /root/ff/database.py
import sqlite3
import json
from config import DB_FILE
DB_FILE = "fomo.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, init_data TEXT, username TEXT,
                    proxy_port INTEGER, is_recruit_active INTEGER DEFAULT 0,
                    is_clan_active INTEGER DEFAULT 0,
                    config TEXT DEFAULT '{}',
                    clan_config TEXT DEFAULT '[]'
                )''')
    conn.commit()
    conn.close()

def db_get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def db_add_user(user_id, init_data, username, start_port):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT MAX(proxy_port) FROM users")
    max_port = c.fetchone()[0]
    new_port = start_port if max_port is None else max_port + 1
    c.execute("INSERT OR REPLACE INTO users (user_id, init_data, username, proxy_port, config, clan_config) VALUES (?, ?, ?, ?, COALESCE((SELECT config FROM users WHERE user_id = ?), '{}'), COALESCE((SELECT clan_config FROM users WHERE user_id = ?), '[]'))",
              (user_id, init_data, username, new_port, user_id, user_id))
    conn.commit()
    conn.close()
    return new_port

def db_update_config(user_id, new_config):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET config = ? WHERE user_id = ?", (json.dumps(new_config), user_id))
    conn.commit()
    conn.close()

def db_update_clan_config(user_id, new_clan_config):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET clan_config = ? WHERE user_id = ?", (json.dumps(new_clan_config), user_id))
    conn.commit()
    conn.close()

def db_set_active(user_id, task_type, is_active):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"UPDATE users SET is_{task_type}_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id))
    conn.commit()
    conn.close()

def db_get_all_active():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE is_recruit_active = 1 OR is_clan_active = 1")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def db_get_all_users():
    """Возвращает список всех пользователей для админ-панели."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT user_id, username, init_data, proxy_port FROM users")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]