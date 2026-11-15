"""Orchestrates the tutor agent, session cache, and durable SQLite history."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.tutor_agent import TutorAgent
from app.conversation import database
from app.conversation.chat_memory import ChatSessionMemory


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatNotFoundError(LookupError):
    pass


class TutorChatService:
    def __init__(self, agent: TutorAgent | None = None):
        self.agent = agent or TutorAgent()
        self.memory = ChatSessionMemory(max_messages=12)

    def create_chat(self, lesson_title: str, lesson_content: str) -> dict:
        chat_id = str(uuid4())
        now = utc_now()
        database.create_chat(chat_id, lesson_title, lesson_content, now)
        self.memory.hydrate(chat_id, [])
        return {"chat_id": chat_id, "lesson_title": lesson_title, "created_at": now}

    def _require_chat(self, chat_id: str) -> dict:
        chat = database.get_chat(chat_id)
        if chat is None:
            raise ChatNotFoundError("Tutor chat was not found.")
        return chat

    def _get_history(self, chat_id: str) -> list[dict]:
        cached = self.memory.get(chat_id)
        if cached is not None:
            return cached
        persisted = database.get_messages(chat_id, limit=12)
        self.memory.hydrate(chat_id, persisted)
        return persisted

    def send_message(self, chat_id: str, message: str, mode: str) -> dict:
        chat = self._require_chat(chat_id)
        history = self._get_history(chat_id)
        answer = self.agent.answer(
            lesson_title=chat["lesson_title"],
            lesson_content=chat["lesson_content"],
            history=history,
            question=message,
            mode=mode,
        )
        now = utc_now()
        user_item = {"role": "user", "content": message, "mode": mode, "created_at": now}
        assistant_item = {"role": "assistant", "content": answer, "mode": mode, "created_at": now}
        database.add_message(chat_id, "user", message, mode, now)
        database.add_message(chat_id, "assistant", answer, mode, now)
        self.memory.append(chat_id, user_item)
        self.memory.append(chat_id, assistant_item)
        return {"chat_id": chat_id, "answer": answer, "mode": mode, "created_at": now}

    def get_history(self, chat_id: str) -> dict:
        chat = self._require_chat(chat_id)
        messages = database.get_messages(chat_id, limit=100)
        return {
            "chat_id": chat_id,
            "lesson_title": chat["lesson_title"],
            "messages": messages,
        }

    def list_chats(self) -> list[dict]:
        return [
            {
                "chat_id": item["id"],
                "lesson_title": item["lesson_title"],
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
            for item in database.list_chats()
        ]

    def create_quiz(self, chat_id: str) -> dict:
        chat = self._require_chat(chat_id)
        quiz = self.agent.generate_quiz(
            lesson_title=chat["lesson_title"],
            lesson_content=chat["lesson_content"],
        )
        quiz_data = quiz.model_dump()
        now = utc_now()
        database.set_active_quiz(chat_id, quiz_data, now)
        question_text = "Quiz: " + quiz.question + "\n" + "\n".join(
            f"{option.id}. {option.text}" for option in quiz.options
        )
        database.add_message(chat_id, "assistant", question_text, "quiz", now)
        self.memory.append(chat_id, {
            "role": "assistant", "content": question_text,
            "mode": "quiz", "created_at": now,
        })
        return {
            "chat_id": chat_id,
            "question": quiz.question,
            "options": [option.model_dump() for option in quiz.options],
        }

    def submit_quiz_answer(self, chat_id: str, option_id: str) -> dict:
        chat = self._require_chat(chat_id)
        raw_quiz = chat.get("active_quiz_json")
        if not raw_quiz:
            raise ValueError("There is no unanswered quiz for this chat. Generate a quiz first.")
        quiz = json.loads(raw_quiz)
        correct = option_id == quiz["correct_option"]
        feedback = (
            "That's right! Well done. " if correct
            else f"Not quite. The correct option is {quiz['correct_option']}. "
        ) + quiz["explanation"]
        now = utc_now()
        user_text = f"My quiz answer: {option_id}"
        database.add_message(chat_id, "user", user_text, "quiz_answer", now)
        database.add_message(chat_id, "assistant", feedback, "quiz_feedback", now)
        database.set_active_quiz(chat_id, None, now)
        self.memory.append(chat_id, {
            "role": "user", "content": user_text,
            "mode": "quiz_answer", "created_at": now,
        })
        self.memory.append(chat_id, {
            "role": "assistant", "content": feedback,
            "mode": "quiz_feedback", "created_at": now,
        })
        return {
            "chat_id": chat_id,
            "correct": correct,
            "selected_option": option_id,
            "correct_option": quiz["correct_option"],
            "explanation": quiz["explanation"],
            "feedback": feedback,
        }
