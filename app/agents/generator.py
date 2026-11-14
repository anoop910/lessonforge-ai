
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage

from app.llm.zoho_quickml import ZohoQuickMLChat
from app.agents.schemas import LessonPlan
from app.prompts.generator_prompt import (
    GENERATOR_PROMPT,
    parser
)


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

        prompt_values = {
            "topic": topic,
            "learner_profile": learner_profile,
            "lesson_minutes": lesson_minutes,
            "min_subtopics": min_subtopics,
            "max_subtopics": max_subtopics,
            "format_instructions": parser.get_format_instructions()
        }

        messages = GENERATOR_PROMPT.format_messages(
            **prompt_values
        )

        for attempt in range(self.MAX_RETRIES + 1):

            print(f"\nPlanning attempt: {attempt + 1}")

            try:

                response = self.llm.invoke(messages)

                plan = parser.parse(response.content)

                # Validate requested topic
                if plan.topic.strip().casefold() != topic.strip().casefold():
                    raise ValueError(
                        f"Wrong topic: expected '{topic}', "
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

            except (OutputParserException, ValueError) as error:

                print("Lesson plan validation: FAILED")
                print(error)

                if attempt == self.MAX_RETRIES:
                    raise RuntimeError(
                        "Lesson planning failed after "
                        "maximum retries."
                    ) from error

                messages.extend([
                    response if "response" in locals() else HumanMessage(
                        content="No previous response available."
                    ),
                    HumanMessage(
                        content=f"""
Your previous lesson plan failed validation.

Original topic: {topic}

Validation error:
{str(error)}

Correct the lesson plan.

Requirements:
- Follow the exact requested topic.
- Include every required JSON field.
- Follow the subtopic count limits.
- Use all four required subtopic types.
- Ensure dependencies refer only to earlier subtopics.
- Return only valid JSON.
"""
                    )
                ])

        raise RuntimeError("Unexpected lesson planning failure.")
