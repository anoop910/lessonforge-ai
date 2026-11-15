"""Small SQLite repository for tutor chats; independent of lesson generation."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(os.getenv("LESSONFORGE_TUTOR_DB", "lessonforge_tutor.db"))


def _connect() -> sqlite3.Connection:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DEFAULT_DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_tutor_db() -> None:
    with _connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tutor_chats (
                id TEXT PRIMARY KEY,
                lesson_title TEXT NOT NULL,
                lesson_content TEXT NOT NULL,
                active_quiz_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tutor_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                mode TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES tutor_chats(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tutor_messages_chat_id_id
            ON tutor_messages(chat_id, id);
            """
        )


def create_chat(chat_id: str, lesson_title: str, lesson_content: str, now: str) -> None:
    with _connect() as connection:
        connection.execute(
            """INSERT INTO tutor_chats
               (id, lesson_title, lesson_content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, lesson_title, lesson_content, now, now),
        )


def get_chat(chat_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM tutor_chats WHERE id = ?", (chat_id,)
        ).fetchone()
    return dict(row) if row else None


def list_chats(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """SELECT id, lesson_title, created_at, updated_at
               FROM tutor_chats ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_message(
    chat_id: str, role: str, content: str, mode: str | None, now: str
) -> None:
    with _connect() as connection:
        connection.execute(
            """INSERT INTO tutor_messages
               (chat_id, role, content, mode, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, role, content, mode, now),
        )
        connection.execute(
            "UPDATE tutor_chats SET updated_at = ? WHERE id = ?",
            (now, chat_id),
        )


def get_messages(chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """SELECT role, content, mode, created_at
               FROM (
                   SELECT id, role, content, mode, created_at
                   FROM tutor_messages WHERE chat_id = ?
                   ORDER BY id DESC LIMIT ?
               ) ORDER BY id ASC""",
            (chat_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def set_active_quiz(chat_id: str, quiz: dict[str, Any] | None, now: str) -> None:
    encoded = json.dumps(quiz, ensure_ascii=False) if quiz is not None else None
    with _connect() as connection:
        connection.execute(
            "UPDATE tutor_chats SET active_quiz_json = ?, updated_at = ? WHERE id = ?",
            (encoded, now, chat_id),
        )


def decode_active_quiz(chat: dict[str, Any]) -> dict[str, Any] | None:
    raw = chat.get("active_quiz_json")
    return json.loads(raw) if raw else None
