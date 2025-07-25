import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict
import os

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv('SQLITE_DB_PATH', 'sessions.db')
        self.init_db()

    def get_connection(self):
        # Ensure the directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE,
                    url TEXT NOT NULL,
                    selectors TEXT NOT NULL,
                    interval INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    last_element_texts TEXT
                )
            """)
            
            # Check if last_element_texts column exists and add it if it doesn't
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'last_element_texts' not in columns:
                cursor.execute("ALTER TABLE sessions ADD COLUMN last_element_texts TEXT DEFAULT '{}'")
                
            conn.commit()

    def add_session(self, chat_id: int, url: str, selectors: List[str], interval: int) -> bool:
        if self.get_active_sessions_count() >= 5:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO sessions (chat_id, url, selectors, interval, start_time, last_element_texts) VALUES (?, ?, ?, ?, ?, ?)",
                    (chat_id, url, json.dumps(selectors), interval, datetime.now().isoformat(), "{}")
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_session(self, chat_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
            return cursor.rowcount > 0

    def get_session(self, chat_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, url, selectors, interval, start_time, last_element_texts FROM sessions WHERE chat_id = ?",
                (chat_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "url": row[1],
                    "selectors": json.loads(row[2]),
                    "interval": row[3],
                    "start_time": row[4],
                    "last_element_texts": json.loads(row[5] or "{}")
                }
            return None

    def update_element_texts(self, chat_id: int, texts: Dict[str, str]) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET last_element_texts = ? WHERE chat_id = ?",
                (json.dumps(texts), chat_id)
            )
            return cursor.rowcount > 0

    def get_active_sessions_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]

    def get_all_active_sessions(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chat_id, url, selectors, interval, start_time, last_element_texts FROM sessions"
            )
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "chat_id": row[0],
                    "url": row[1],
                    "selectors": json.loads(row[2]),
                    "interval": row[3],
                    "start_time": row[4],
                    "last_element_texts": json.loads(row[5] or "{}")
                })
            return sessions 