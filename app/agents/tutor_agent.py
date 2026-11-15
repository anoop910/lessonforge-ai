"""LangChain-powered tutor agent with bounded lesson and conversation context."""

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.conversation.schemas import GeneratedQuiz
from app.llm.zoho_quickml import ZohoQuickMLChat
from app.prompts.tutor_prompt import (
    MODE_INSTRUCTIONS,
    QUIZ_GENERATION_PROMPT,
    TUTOR_SYSTEM_PROMPT,
)


class TutorOutputError(RuntimeError):
    """The model returned a response that did not match the tutor schema."""


class TutorAgent:
    # These are conservative application-side limits, not Zoho's published limits.
    # The endpoint rejected ~10.1k prompt characters in the user's logs.
    MAX_LESSON_CONTEXT_CHARS = 2500
    MAX_QUIZ_CONTEXT_CHARS = 3500
    MAX_HISTORY_MESSAGES = 6  # three previous user/assistant turns
    MAX_HISTORY_ITEM_CHARS = 400
    MAX_QUESTION_CHARS = 1200
    MAX_TOTAL_MESSAGE_CHARS = 7000

    STOP_WORDS = {
        "about", "after", "again", "also", "and", "are", "because", "been",
        "before", "being", "between", "but", "can", "could", "does", "explain",
        "for", "from", "give", "have", "into", "just", "lesson", "like", "make",
        "more", "please", "show", "some", "that", "the", "their", "them", "then",
        "there", "these", "they", "this", "those", "through", "using", "very",
        "what", "when", "where", "which", "with", "would", "your", "you",
    }

    def __init__(self, llm=None):
        self.llm = llm or ZohoQuickMLChat()

    @classmethod
    def _keywords(cls, text: str) -> set[str]:
        words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower()))
        return words - cls.STOP_WORDS

    @classmethod
    def _select_lesson_context(
        cls, lesson_content: str, question: str, max_chars: int
    ) -> str:
        """Select question-relevant lesson paragraphs instead of resending the whole lesson."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", lesson_content) if p.strip()]
        if not paragraphs:
            return lesson_content[:max_chars]

        query_terms = cls._keywords(question)
        ranked = []
        for index, paragraph in enumerate(paragraphs):
            terms = cls._keywords(paragraph)
            score = len(query_terms & terms)
            # Keep the opening paragraph as basic lesson context.
            if index == 0:
                score += 2
            ranked.append((score, index, paragraph))

        # Prefer relevant paragraphs; keep original lesson order in the final context.
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected: list[tuple[int, str]] = []
        used = 0
        for _, index, paragraph in ranked:
            separator_cost = 2 if selected else 0
            remaining = max_chars - used - separator_cost
            if remaining <= 0:
                break
            if len(paragraph) > remaining:
                if not selected:
                    selected.append((index, paragraph[:remaining]))
                break
            selected.append((index, paragraph))
            used += len(paragraph) + separator_cost

        selected.sort(key=lambda item: item[0])
        return "\n\n".join(paragraph for _, paragraph in selected)[:max_chars]

    @staticmethod
    def _message_chars(messages) -> int:
        return sum(len(message.content) for message in messages if isinstance(message.content, str))

    def answer(
        self,
        *,
        lesson_title: str,
        lesson_content: str,
        history: list[dict],
        question: str,
        mode: str = "chat",
    ) -> str:
        safe_question = question[:self.MAX_QUESTION_CHARS]
        lesson_context = self._select_lesson_context(
            lesson_content, safe_question, self.MAX_LESSON_CONTEXT_CHARS
        )
        system_prompt = TUTOR_SYSTEM_PROMPT.format(
            lesson_title=lesson_title[:200],
            lesson_content=lesson_context,
        )
        system_prompt += "\n\nCURRENT RESPONSE STYLE:\n" + MODE_INSTRUCTIONS[mode]

        history_messages = []
        for item in history[-self.MAX_HISTORY_MESSAGES:]:
            content = str(item.get("content", ""))[:self.MAX_HISTORY_ITEM_CHARS]
            if not content:
                continue
            if item.get("role") == "user":
                history_messages.append(HumanMessage(content=content))
            elif item.get("role") == "assistant":
                history_messages.append(AIMessage(content=content))

        # Drop oldest context first if the assembled prompt is still above our budget.
        messages = [SystemMessage(content=system_prompt), *history_messages,
                    HumanMessage(content=safe_question)]
        while len(messages) > 2 and self._message_chars(messages) > self.MAX_TOTAL_MESSAGE_CHARS:
            messages.pop(1)

        # Keep a hard guard even if a future prompt edit adds more instructions.
        if self._message_chars(messages) > self.MAX_TOTAL_MESSAGE_CHARS:
            available = max(500, self.MAX_TOTAL_MESSAGE_CHARS - len(system_prompt) - 100)
            safe_question = safe_question[:available]
            messages[-1] = HumanMessage(content=safe_question)

        response = self.llm.invoke(messages)
        content = response.content
        if not isinstance(content, str) or not content.strip():
            raise TutorOutputError("The tutor model returned an empty answer.")
        return content.strip()

    def generate_quiz(self, *, lesson_title: str, lesson_content: str) -> GeneratedQuiz:
        quiz_context = self._select_lesson_context(
            lesson_content,
            "main concepts definitions examples and important points",
            self.MAX_QUIZ_CONTEXT_CHARS,
        )
        prompt = QUIZ_GENERATION_PROMPT.format(
            lesson_title=lesson_title[:200],
            lesson_content=quiz_context,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        raw = response.content
        if not isinstance(raw, str):
            raise TutorOutputError("The quiz response was not text.")

        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise TutorOutputError("The model did not return a JSON quiz object.")

        try:
            data = json.loads(cleaned[start:end + 1])
            return GeneratedQuiz.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise TutorOutputError(
                "The model returned an invalid quiz. Please generate another one."
            ) from exc
