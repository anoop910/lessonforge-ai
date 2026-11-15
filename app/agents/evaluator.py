import re
import time

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from app.agents.schemas import LessonEvaluation
from app.llm.zoho_quickml import (
    ZohoQuickMLChat,
    ZohoRequestTooLargeError,
)
from app.prompts.evaluator_prompt import (
    EVALUATOR_PROMPT,
    parser
)


class EvaluationError(RuntimeError):
    """Raised when the judge cannot return a valid evaluation."""


MAX_EVALUATOR_PREVIOUS_CHARS = 1400
MAX_EVALUATOR_SOURCE_FACTS_CHARS = 1000
MAX_EVALUATOR_SOURCE_FACTS = 6


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " ...[context shortened]"


# The same six criteria are applied to every section, but a recap section
# cannot be asked to teach everything again. These rules keep each
# criterion binary while making it fair for the section type.
TYPE_RULES = {
    "foundation": (
        "This section introduces the topic. Apply every criterion in full."
    ),
    "core": (
        "This section explains how it works. Apply every criterion in full."
    ),
    "application": (
        "This section shows the idea in use. Apply every criterion in full. "
        "The example must be concrete and worked through step by step."
    ),
    "wrap-up": (
        "This section is a recap, not new teaching. Adjust the criteria:\n"
        "- required_coverage: PASS if every must_teach point is recapped "
        "briefly in plain words. It does not need full detail again.\n"
        "- jargon_explanation: a term explained anywhere in the previously "
        "taught content counts as explained. FAIL only for a term that is "
        "used but never explained anywhere.\n"
        "- example_quality: PASS if the section points back to an example "
        "from the previously taught content, or gives a short new one. "
        "Do not require a new full example.\n"
        "- accuracy, beginner_friendly, simple_language: apply in full."
    ),
}


class LessonEvaluator:

    # Total tries for ONE judging call (first try + retries).
    MAX_ATTEMPTS = 3

    # Seconds to wait after a failed API call (grows each attempt).
    RETRY_DELAY_SECONDS = 2

    def __init__(self):
        self.llm = ZohoQuickMLChat()

    @staticmethod
    def _clean(text: str) -> str:
        # Reasoning models may add <think>...</think> before the JSON.
        return re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL
        ).strip()

    def evaluate(
        self,
        topic,
        learner_profile,
        subtopic,
        generated_content,
        source_facts,
        previous_content=""
    ) -> LessonEvaluation:

        bounded_facts = []
        used_chars = 0
        for fact in list(source_facts or [])[:MAX_EVALUATOR_SOURCE_FACTS]:
            fact = _clip(str(fact), 300)
            remaining = MAX_EVALUATOR_SOURCE_FACTS_CHARS - used_chars
            if remaining <= 0:
                break
            fact = _clip(fact, remaining)
            bounded_facts.append(f"- {fact}")
            used_chars += len(fact) + 2

        base_messages = EVALUATOR_PROMPT.format_messages(
            topic=topic,
            learner_profile=_clip(learner_profile, 500),
            subtopic_json=subtopic.model_dump_json(indent=2),
            generated_content=generated_content,
            previous_content=(
                _clip(previous_content, MAX_EVALUATOR_PREVIOUS_CHARS)
                or "None. This is the first section of the lesson."
            ),
            type_rules=TYPE_RULES.get(subtopic.type, TYPE_RULES["core"]),
            source_facts="\n".join(bounded_facts) or "None provided",
            format_instructions=parser.get_format_instructions(),
        )

        messages = base_messages
        last_error = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):

            # ---- 1. Call the judge (network / API problems) ----
            try:
                response = self.llm.invoke(messages)

            except ZohoRequestTooLargeError as error:
                # This is a deterministic request-size problem. Retrying the
                # identical payload cannot fix it. Let the workflow flag the
                # section for review instead of wasting more API calls.
                raise EvaluationError(
                    "Judge request is too large for Zoho QuickML. "
                    "Reduce dependency context, source facts, or prompt size. "
                    f"Details: {error}"
                ) from error

            except (RuntimeError, ValueError) as error:
                last_error = error

                print(
                    f"Judge API error "
                    f"(attempt {attempt}/{self.MAX_ATTEMPTS}): {error}"
                )

                if attempt < self.MAX_ATTEMPTS:
                    time.sleep(self.RETRY_DELAY_SECONDS * attempt)

                continue

            # ---- 2. Parse and validate the answer ----
            raw = self._clean(response.content)

            try:
                return parser.parse(raw)

            except (OutputParserException, ValidationError, ValueError) as error:
                last_error = error

                print(
                    f"Judge output invalid "
                    f"(attempt {attempt}/{self.MAX_ATTEMPTS}): "
                    f"{str(error)[:300]}"
                )

                # Retry from the original prompt with a short correction note.
                # Do not append the previous full model response: that makes
                # every retry larger and can trigger MORE_THAN_MAX_LENGTH.
                messages = base_messages + [
                    HumanMessage(
                        content=(
                            "Your previous response did not match the required "
                            "JSON schema.\n"
                            f"Validation problem: {str(error)[:350]}\n\n"
                            "Return the same evaluation as valid JSON only. "
                            "Include exactly one entry for each of the six "
                            "criteria. Each result must be PASS or FAIL. "
                            "Every entry needs evidence; every FAIL needs "
                            "specific feedback. Do not include scores."
                        )
                    )
                ]

        raise EvaluationError(
            f"Judge failed after {self.MAX_ATTEMPTS} attempts. "
            f"Last error: {last_error}"
        ) from last_error