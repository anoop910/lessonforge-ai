
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage

from app.llm.zoho_quickml import ZohoQuickMLChat, ZohoRequestTooLargeError
from app.agents.schemas import LessonPlan
from app.prompts.generator_prompt import (
    GENERATOR_PROMPT,
    parser
)


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " ...[context shortened]"


class LessonPlanner:

    MAX_RETRIES = 2

    def __init__(self):

        self.llm = ZohoQuickMLChat()

    def generate(
        self,
        topic: str,
        learner_profile: str,
        lesson_minutes: int = 20,
        min_subtopics: int = 5,
        max_subtopics: int = 8
    ) -> LessonPlan:

        if min_subtopics < 4:
            raise ValueError(
                "Minimum subtopics must be at least 4 "
                "to cover all four teaching types."
            )

        if min_subtopics > max_subtopics:
            raise ValueError(
                "min_subtopics cannot exceed max_subtopics"
            )

        # Keep user-provided context bounded. Lesson duration and requested
        # section count remain unchanged; these limits only affect prompt text.
        requested_topic = topic
        learner_profile = _clip(learner_profile, 600)

        prompt_values = {
            "topic": topic,
            "learner_profile": learner_profile,
            "lesson_minutes": lesson_minutes,
            "min_subtopics": min_subtopics,
            "max_subtopics": max_subtopics,
            "format_instructions": parser.get_format_instructions()
        }

        base_messages = GENERATOR_PROMPT.format_messages(
            **prompt_values
        )
        messages = base_messages

        for attempt in range(self.MAX_RETRIES + 1):

            print(f"\nPlanning attempt: {attempt + 1}")

            try:

                response = self.llm.invoke(messages)

                plan = parser.parse(response.content)

                # Validate requested topic
                if plan.topic.strip().casefold() != requested_topic.strip().casefold():
                    raise ValueError(
                        f"Wrong topic: expected '{requested_topic}', "
                        f"received '{plan.topic}'"
                    )

                # Validate subtopic count
                count = len(plan.subtopics)

                if not min_subtopics <= count <= max_subtopics:
                    raise ValueError(
                        f"Expected between {min_subtopics} "
                        f"and {max_subtopics} subtopics. "
                        f"Received {count}."
                    )

                print("Lesson plan validation: PASSED")

                return plan

            except ZohoRequestTooLargeError:
                # A repeated identical oversized request cannot succeed.
                # Do not consume the planner's quality-retry budget.
                raise

            except (OutputParserException, ValueError) as error:

                print("Lesson plan validation: FAILED")
                print(error)

                if attempt == self.MAX_RETRIES:
                    raise RuntimeError(
                        "Lesson planning failed after "
                        "maximum retries."
                    ) from error

                # Rebuild from the original prompt each time. Do NOT append
                # the previous full plan: its size grows with section count
                # and made later retry requests much larger.
                messages = base_messages + [
                    HumanMessage(
                        content=(
                            "The previous plan did not pass validation. "
                            "Correct it using this brief issue: "
                            f"{_clip(str(error), 350)}. "
                            "Keep the exact topic and requested subtopic "
                            "count range, include all four required types, "
                            "use earlier IDs only in builds_on, and return "
                            "valid JSON only."
                        )
                    )
                ]

        raise RuntimeError("Unexpected lesson planning failure.")
