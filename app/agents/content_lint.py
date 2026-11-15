"""
Cheap, deterministic checks that run on a draft BEFORE the LLM judge.

They only look for problems that code can see reliably, so a weak draft is
fixed without spending a judge call, and the judge sees a cleaner draft.
Each function returns plain-English issues that can be fed back to the
generator.
"""

import re

MAX_SENTENCE_WORDS = 25
MIN_WORDS = 60
MAX_WORDS = 500
MIN_POINT_COVERAGE = 0.35

STOPWORDS = set(
    "the a an of to in on and or is are was were be been it its this that "
    "for with as by at from can will you your they them their there these "
    "those what which who how why when where about into than then also "
    "more most very not no any some such have has had does did done make "
    "makes made use used using".split()
)

META_PHRASES = (
    "in this section",
    "in this lesson",
    "let us dive",
    "let's dive",
    "let's get started",
    "welcome to",
)


def strip_leading_heading(text: str) -> str:
    """The model sometimes writes the section title even when told not to."""
    lines = text.strip().splitlines()

    while lines and (not lines[0].strip() or re.match(r"^\s{0,3}#{1,6}\s", lines[0])):
        lines.pop(0)

    return "\n".join(lines).strip()


def _plain(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"[*_`#>]", "", text)
    text = re.sub(r"^\s*(\d+[.)]|[-+•])\s+", "", text, flags=re.MULTILINE)
    return text


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", _plain(text))
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text)


def _stems(text: str) -> set[str]:
    return {
        w.lower()[:5]
        for w in _words(text)
        if len(w) >= 4 and w.lower() not in STOPWORDS
    }


def _is_defined(term: str, text: str) -> bool:
    """True if the first use of `term` comes with a real definition."""
    plain = _plain(text)
    low = plain.lower()
    t = re.escape(term.lower().strip())

    match = re.search(t, low)
    if not match:
        return False

    # Look at the sentence holding the first use, plus the next one.
    sentences = _sentences(text)
    holder = next(
        (i for i, s in enumerate(sentences) if re.search(t, s.lower())), None
    )
    if holder is None:
        return False

    window = " ".join(sentences[holder: holder + 2]).lower()

    if re.search(
        rf"{t}(?:s|es)?\s+(?:is|are|means|refers to|stands for)\b", window
    ):
        return True

    if re.search(rf"(?:called|known as|named|call(?:s)? this)\s+{t}", window):
        return True

    # A bracket note counts only when the sentence also says something
    # else. "Acid (a thing that ...)." alone is just a label.
    sentence = sentences[holder].lower()

    if re.search(rf"{t}(?:s|es)?\s*\(", sentence):
        outside = re.sub(r"\([^)]*\)", " ", sentence)
        outside = re.sub(t, " ", outside)

        if len(_words(outside)) >= 3:
            return True

    return False


def lint_section(content: str, subtopic, previous_content: str = "") -> list[str]:
    """Return a list of problems found in a drafted section (empty = clean)."""
    issues = []

    words = _words(_plain(content))

    if len(words) < MIN_WORDS:
        issues.append(
            f"The section is too short ({len(words)} words). "
            "Explain every point fully."
        )

    if len(words) > MAX_WORDS:
        issues.append(
            f"The section is too long ({len(words)} words). "
            "Keep it focused on the plan."
        )

    # 1. Long sentences
    long_ones = [
        s for s in _sentences(content) if len(_words(s)) > MAX_SENTENCE_WORDS
    ]

    if long_ones:
        shown = "; ".join(f'"{s[:90]}..."' for s in long_ones[:2])
        issues.append(
            f"{len(long_ones)} sentence(s) are longer than "
            f"{MAX_SENTENCE_WORDS} words. Split them. Example: {shown}"
        )

    # 2. Key terms must be defined at first use (recaps only point back)
    if subtopic.type != "wrap-up":
        earlier = previous_content.lower()

        for term in subtopic.key_terms:
            if term.lower().strip() in earlier:
                continue  # taught earlier

            if not _is_defined(term, content):
                issues.append(
                    f"Define '{term}' in a complete, clear sentence at its "
                    "first use. Use correct grammar and singular/plural "
                    "agreement; do not force an article such as 'a' before "
                    "a plural term."
                )

    # 3. A planned point that seems to be missing
    content_stems = _stems(content)

    for point in subtopic.must_teach:
        wanted = _stems(point)

        if len(wanted) < 2:
            continue

        if len(wanted & content_stems) / len(wanted) < MIN_POINT_COVERAGE:
            issues.append(
                f'This planned point seems to be missing: "{point}". '
                "State it in its own clear sentence."
            )

    # 4. Filler and mini-summaries
    low = _plain(content).lower()

    if subtopic.type != "wrap-up":
        found = [p for p in META_PHRASES if p in low]

        if found:
            issues.append(
                f"Remove filler such as '{found[0]}'. "
                "Start teaching directly."
            )

        if re.search(r"^\s*\W*summary\b", content, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(
                "Remove the 'Summary' block. "
                "Only the wrap-up section gives a summary."
            )

    return issues