"""In-process session cache backed by the persistent SQLite message history."""

from collections import defaultdict
from threading import RLock


class ChatSessionMemory:
    def __init__(self, max_messages: int = 12):
        self.max_messages = max_messages
        self._sessions: dict[str, list[dict]] = defaultdict(list)
        self._lock = RLock()

    def get(self, chat_id: str) -> list[dict] | None:
        with self._lock:
            if chat_id not in self._sessions:
                return None
            return list(self._sessions[chat_id])

    def hydrate(self, chat_id: str, messages: list[dict]) -> None:
        with self._lock:
            self._sessions[chat_id] = list(messages[-self.max_messages:])

    def append(self, chat_id: str, message: dict) -> None:
        with self._lock:
            self._sessions[chat_id].append(message)
            self._sessions[chat_id] = self._sessions[chat_id][-self.max_messages:]

    def clear(self, chat_id: str) -> None:
        with self._lock:
            self._sessions.pop(chat_id, None)
