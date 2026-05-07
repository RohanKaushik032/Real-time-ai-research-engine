# ===== IMPORTS =====
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger("database")

DB_PATH = "db.sqlite"


# =========================
# CONNECTION
# =========================
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB ERROR: {e}")
        raise
    finally:
        conn.close()


# =========================
# INIT DB
# =========================
def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT,
            is_pinned INTEGER DEFAULT 0,
            share_id TEXT,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT,
            FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id TEXT PRIMARY KEY,
            topic TEXT,
            summary TEXT,
            full_report TEXT,
            is_bookmarked INTEGER DEFAULT 0,
            created_at TEXT
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chats_time ON chats(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chats_title ON chats(title)")

init_db()


# =========================
# CHAT
# =========================
def create_chat(chat_id, title):
    with get_connection() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO chats (id, title, created_at)
        VALUES (?, ?, ?)
        """, (
            chat_id,
            (title or "New Chat")[:100],
            datetime.now(timezone.utc).isoformat()
        ))


# =========================
# MESSAGE (FIXED)
# =========================
VALID_ROLES = {"user", "assistant", "system"}

def save_message(chat_id, role, content):
    if role not in VALID_ROLES:
        logger.warning(f"Invalid role: {role}")
        return

    if not content:
        return

    content = content.strip()[:5000]  # limit size

    with get_connection() as conn:
        conn.execute("""
        INSERT INTO messages (id, chat_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            chat_id,
            role,
            content,
            datetime.now(timezone.utc).isoformat()
        ))


# backward compatibility
add_message = save_message


# =========================
# GET CHATS
# =========================
def get_all_chats(limit=100, offset=0):
    with get_connection() as conn:
        rows = conn.execute("""
        SELECT id, title, is_pinned
        FROM chats
        ORDER BY is_pinned DESC, created_at DESC
        LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

    return [dict(r) for r in rows]


def search_chats(query):
    with get_connection() as conn:
        rows = conn.execute("""
        SELECT id, title, is_pinned
        FROM chats
        WHERE title LIKE ?
        ORDER BY is_pinned DESC, created_at DESC
        """, (f"%{query}%",)).fetchall()

    return [dict(r) for r in rows]


def get_chat(chat_id):
    with get_connection() as conn:
        rows = conn.execute("""
        SELECT role, content
        FROM messages
        WHERE chat_id=?
        ORDER BY created_at ASC
        """, (chat_id,)).fetchall()

    return [dict(r) for r in rows]


# =========================
# DELETE / UPDATE
# =========================
def delete_chat(chat_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))


def update_chat_title(chat_id, title):
    with get_connection() as conn:
        conn.execute("""
        UPDATE chats SET title=? WHERE id=?
        """, ((title or "Untitled")[:100], chat_id))


def toggle_pin(chat_id):
    with get_connection() as conn:
        conn.execute("""
        UPDATE chats
        SET is_pinned = CASE WHEN is_pinned=1 THEN 0 ELSE 1 END
        WHERE id=?
        """, (chat_id,))


# =========================
# SHARING
# =========================
def create_share(chat_id):
    share_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute("""
        UPDATE chats SET share_id=? WHERE id=?
        """, (share_id, chat_id))

    return share_id


def get_chat_by_share(share_id):
    with get_connection() as conn:
        row = conn.execute("""
        SELECT id FROM chats WHERE share_id=?
        """, (share_id,)).fetchone()

        if not row:
            return []

    return get_chat(row["id"])


# =========================
# INSIGHTS
# =========================
def save_insight(topic, report):
    with get_connection() as conn:
        conn.execute("""
        INSERT INTO insights (id, topic, summary, full_report, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            topic,
            report[:200],
            report,
            datetime.now(timezone.utc).isoformat()
        ))


def get_insights(limit=50):
    with get_connection() as conn:
        rows = conn.execute("""
        SELECT * FROM insights
        ORDER BY created_at DESC
        LIMIT ?
        """, (limit,)).fetchall()

    return [dict(r) for r in rows]


def toggle_bookmark(insight_id):
    with get_connection() as conn:
        conn.execute("""
        UPDATE insights
        SET is_bookmarked = CASE WHEN is_bookmarked=1 THEN 0 ELSE 1 END
        WHERE id=?
        """, (insight_id,))