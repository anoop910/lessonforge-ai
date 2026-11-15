from langchain_core.output_parsers import StrOutputParser

from app.agents.content_lint import lint_section, strip_leading_heading
from app.llm.zoho_quickml import ZohoQuickMLChat
from app.prompts.content_prompt import CONTENT_PROMPT


MAX_PREVIOUS_CONTEXT_CHARS = 2500
MAX_SOURCE_FACTS_CHARS = 1400
MAX_EXTRA_RULES = 4
MAX_EXTRA_RULE_CHARS = 350
MAX_PREVIOUS_DRAFT_CHARS = 2200
MAX_REVISION_NOTES = 4
MAX_REVISION_NOTE_CHARS = 350


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " ...[truncated]"


def _format_bounded_items(items, max_items, max_item_chars, total_chars):
    formatted = []
    used = 0
    for item in list(items or [])[:max_items]:
        value = _clip(str(item), max_item_chars)
        if not value:
            continue
        remaining = total_chars - used
        if remaining <= 0:
            break
        value = _clip(value, remaining)
        formatted.append(f"- {value}")
        used += len(value) + 2
    return "\n".join(formatted) or "None provided"


def build_checklist(subtopic, previous_content: str = "") -> str:
    """A numbered list of exactly what this section must contain."""
    lines = []

    for point in subtopic.must_teach:
        lines.append(
            f'State this point in its own clear, direct sentence: "{point}"'
        )

    if subtopic.type == "wrap-up":
        lines.append(
            "Recap each earlier section briefly in plain words and point "
            "back to the examples already used. Do not define new terms."
        )
    else:
        earlier = previous_content.lower()

        new_terms = [
            t for t in subtopic.key_terms if t.lower().strip() not in earlier
        ]

        if new_terms:
            lines.append(
                "Define each of these terms in one full sentence at its "
                "first use, before using it again: " + ", ".join(new_terms)
            )

        lines.append(
            "Give one concrete example, worked through step by step, "
            f"based on: {subtopic.example_idea}. "
            "End it with one sentence saying what it shows."
        )

    lines.append("Stay inside this section. Do not teach later sections.")

    return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, start=1))


def build_revision_block(previous_attempt, notes) -> str:
    """Build a compact revision instruction without resending a huge draft."""
    notes = [n.strip() for n in (notes or []) if n and n.strip()]
    notes = notes[:MAX_REVISION_NOTES]

    if not previous_attempt or not notes:
        return ""

    problems = "\n".join(
        f"- {_clip(note, MAX_REVISION_NOTE_CHARS)}"
        for note in notes
    )
    previous_attempt = _clip(
        previous_attempt, MAX_PREVIOUS_DRAFT_CHARS
    )

    return f"""### REVISION: FIX YOUR PREVIOUS VERSION
Your previous version (may be shortened):
<previous_version>
{previous_attempt}
</previous_version>

Problems found by the reviewer:
{problems}

How to revise:
- Fix every listed problem.
- Do not remove any point that was already taught correctly.
- Keep the revision focused. Do not add unrelated material.
- Return the complete corrected section."""



class LessonContentGenerator:

    # Extra draft rounds when the code check finds a problem. These are
    # cheaper than a judge rejection and happen before the judge sees it.
    MAX_LINT_FIXES = 1

    def __init__(self):
        self.llm = ZohoQuickMLChat()

        self.chain = (
            CONTENT_PROMPT
            | self.llm
            | StrOutputParser()
        )

    def _draft(
        self,
        topic,
        learner_profile,
        subtopic,
        previous_content,
        source_facts,
        extra_rules,
        previous_attempt,
        notes,
    ) -> str:

        bounded_previous_content = _clip(
            previous_content, MAX_PREVIOUS_CONTEXT_CHARS
        )

        text = self.chain.invoke({
            "topic": topic,
            "learner_profile": learner_profile,
            "subtopic_json": subtopic.model_dump_json(indent=2),
            "subtopic_title": subtopic.title,
            "section_checklist": build_checklist(
                subtopic, bounded_previous_content
            ),
            "previous_content": bounded_previous_content or "None.",
            "source_facts": _format_bounded_items(
                source_facts,
                max_items=8,
                max_item_chars=350,
                total_chars=MAX_SOURCE_FACTS_CHARS,
            ),
            "extra_rules": _format_bounded_items(
                extra_rules,
                max_items=MAX_EXTRA_RULES,
                max_item_chars=MAX_EXTRA_RULE_CHARS,
                total_chars=1500,
            ),
            "revision_block": build_revision_block(
                previous_attempt, notes
            ),
        })

        return strip_leading_heading(text)

    def generate_subtopic(
        self,
        topic,
        learner_profile,
        subtopic,
        previous_content,
        source_facts,
        extra_rules,
        previous_attempt=None,
        revision_notes=None,
    ):
        """
        Write one section.

        previous_attempt + revision_notes are set when the judge rejected
        the last version: the model then edits that version instead of
        starting from scratch.
        """

        basis = previous_attempt
        notes = list(revision_notes or [])
        text = ""

        for round_number in range(self.MAX_LINT_FIXES + 1):

            text = self._draft(
                topic=topic,
                learner_profile=learner_profile,
                subtopic=subtopic,
                previous_content=previous_content,
                source_facts=source_facts,
                extra_rules=extra_rules,
                previous_attempt=basis,
                notes=notes,
            )

            if not text.strip():
                raise ValueError(
                    f"Empty content generated for {subtopic.id}"
                )

            issues = lint_section(text, subtopic, previous_content)

            if not issues:
                return text

            if round_number == self.MAX_LINT_FIXES:
                print(
                    f"Code check still found {len(issues)} issue(s); "
                    "sending to the reviewer anyway."
                )
                return text

            print(
                f"Code check found {len(issues)} issue(s). "
                "Fixing before review:"
            )
            for issue in issues:
                print(f"  - {issue}")

            basis = text
            notes = issues

        return text