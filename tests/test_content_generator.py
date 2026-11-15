"""Offline tests for the content prompt inputs, the code check and the
edit-style revision. No Zoho call is made."""

import pytest

from app.agents.content_generator import (
    LessonContentGenerator, build_checklist, build_revision_block,
)
from app.agents.content_lint import lint_section, strip_leading_heading
from app.agents.schemas import LessonSubtopic


def sub(type_="core", must=None, terms=None, title="Testing"):
    return LessonSubtopic(
        id="S2", title=title, type=type_,
        must_teach=must or ["Litmus paper turns red in acids and blue in bases"],
        key_terms=terms if terms is not None else ["Litmus paper"],
        example_idea="Testing lemon juice and soap water", builds_on=[],
    )


GOOD = (
    "We cannot taste chemicals to test them. We use a safe tool instead. "
    "**Litmus paper** is a special paper that changes color to show if a "
    "liquid is an acid or a base. Litmus paper turns red in acids. It turns "
    "blue in bases. This gives us a safe test that needs no tasting. "
    "Here is a worked example with two liquids.\n"
    "1. Take a piece of litmus paper.\n2. Dip it into lemon juice.\n"
    "3. The paper turns red, so lemon juice is an acid.\n"
    "4. Dip a new piece into soap water.\n5. The paper turns blue, so soap "
    "water is a base.\nThis shows that the color tells us the kind of liquid."
)


# ---------------- code check ----------------

def test_clean_section_has_no_issues():
    assert lint_section(GOOD, sub()) == []


def test_bracket_label_alone_is_not_a_definition():
    bad = GOOD.replace(
        "**Litmus paper** is a special paper that changes color to show if a "
        "liquid is an acid or a base.",
        "**Litmus paper** (a paper that changes color).")
    assert any("Define 'Litmus paper'" in i for i in lint_section(bad, sub()))


def test_inline_bracket_definition_is_accepted():
    ok = GOOD.replace(
        "**Litmus paper** is a special paper that changes color to show if a "
        "liquid is an acid or a base.",
        "We use litmus paper (a paper that changes color) to test liquids.")
    assert not any("Define" in i for i in lint_section(ok, sub()))


def test_term_defined_in_earlier_section_is_not_required_again():
    text = GOOD.replace("**Litmus paper** is a special paper", "The paper is a special paper")
    issues = lint_section(text, sub(), previous_content="Litmus paper is a paper.")
    assert not any("Define" in i for i in issues)


def test_wrap_up_does_not_need_new_definitions():
    issues = lint_section(GOOD, sub("wrap-up", terms=["Neutralization"]))
    assert not any("Define" in i for i in issues)


def test_long_sentence_is_flagged():
    long = ("This is a very long sentence that keeps going and going with many "
            "extra words that a beginner would find hard to follow in one go "
            "because it never stops for a breath at all. ") 
    issues = lint_section(GOOD + " " + long, sub())
    assert any("longer than 25 words" in i for i in issues)


def test_dropped_point_is_flagged():
    # Real S4 failure: the retry silently dropped the human-body point.
    s4 = sub("application", must=["Salts are important for the human body"],
             terms=[])
    text = ("We use salt in food. It keeps food fresh for a long time. Salt "
            "stops bacteria from growing. We put salt on meat and pickles. "
            "Salts are also in medicines and toothpaste. They are in cleaning "
            "products too. For example, we use salt to clean the kitchen sink. "
            "It removes stains and makes the sink shine. This shows that salts "
            "have many everyday uses in the home and in the kitchen.")
    assert any("human body" in i for i in lint_section(text, s4))


def test_filler_and_mini_summary_are_flagged():
    issues = lint_section("In this section we learn.\n" + GOOD + "\n\nSummary: red means acid.", sub())
    text = " ".join(issues)
    assert "filler" in text and "Summary" in text


def test_too_short_is_flagged():
    assert any("too short" in i for i in lint_section("Litmus paper is a paper.", sub()))


def test_leading_heading_is_stripped():
    assert strip_leading_heading("### Testing\n\nHello there") == "Hello there"
    assert strip_leading_heading("Hello\n### not leading") == "Hello\n### not leading"


# ---------------- real drafts from the failed run ----------------

REAL_S1 = ("**Acid** (a substance that tastes sour and can burn the skin).\n\n"
           "Imagine a lemon. It tastes very sour. This sour taste is an acid. "
           "Acids are also in vinegar. They can burn your skin if you touch them.\n\n"
           "**Base** (a substance that tastes bitter and feels slippery).\n\n"
           "Imagine soap. It tastes bitter. It also feels slippery on your hands. "
           "This is a base. Bases are in cleaning products. They help clean dirty things.\n\n"
           "**Example:**\n1.  Taste a small amount of lemon juice. It tastes sour. This is an acid.\n"
           "2.  Touch some soap. It feels slippery. This is a base.")


def test_real_label_only_draft_from_the_log_is_caught():
    s1 = LessonSubtopic(id="S1", title="What are Acids and Bases?", type="foundation",
                        must_teach=["Acids taste sour", "Bases feel slippery"],
                        key_terms=["Acid", "Base"], example_idea="lemon and soap", builds_on=[])
    issues = lint_section(REAL_S1, s1)
    assert any("Define 'Acid'" in i for i in issues)
    assert any("Define 'Base'" in i for i in issues)


# ---------------- prompt inputs ----------------

def test_checklist_lists_every_point_and_new_terms_only():
    s = sub(must=["Point one here", "Point two here"], terms=["Litmus paper", "Indicator"])
    text = build_checklist(s, previous_content="An indicator is a thing.")
    assert "Point one here" in text and "Point two here" in text
    assert "Litmus paper" in text and "Indicator" not in text
    assert text.splitlines()[0].startswith("1.")


def test_wrap_up_checklist_recaps_instead_of_defining():
    text = build_checklist(sub("wrap-up"), "earlier")
    assert "Recap" in text and "Define each" not in text


def test_revision_block_only_when_there_is_something_to_fix():
    assert build_revision_block(None, ["x"]) == ""
    assert build_revision_block("draft", []) == ""
    block = build_revision_block("MY DRAFT", ["[accuracy] fix the claim"])
    assert "MY DRAFT" in block and "fix the claim" in block
    assert "Do not remove any point" in block


# ---------------- generator behaviour ----------------

class FakeChain:
    def __init__(self, replies):
        self.replies = list(replies)
        self.inputs = []

    def invoke(self, values):
        self.inputs.append(values)
        return self.replies.pop(0)


def make_generator(replies):
    gen = LessonContentGenerator.__new__(LessonContentGenerator)
    gen.chain = FakeChain(replies)
    return gen


def generate(gen, **extra):
    return gen.generate_subtopic(
        topic="T", learner_profile="student", subtopic=sub(),
        previous_content="", source_facts=[], extra_rules=[], **extra)


def test_clean_draft_needs_one_call_and_heading_is_removed():
    gen = make_generator(["### Testing\n\n" + GOOD])
    text = generate(gen)
    assert len(gen.chain.inputs) == 1
    assert not text.startswith("#")
    assert gen.chain.inputs[0]["revision_block"] == ""


def test_code_check_issue_triggers_one_edit_before_the_judge():
    bad = GOOD.replace("**Litmus paper** is a special paper that changes color "
                       "to show if a liquid is an acid or a base.", "**Litmus paper** (a paper).")
    gen = make_generator([bad, GOOD])
    text = generate(gen)
    assert text == GOOD
    assert len(gen.chain.inputs) == 2
    second = gen.chain.inputs[1]["revision_block"]
    assert "Define 'Litmus paper'" in second and "**Litmus paper** (a paper)." in second


def test_code_check_cannot_loop_forever():
    bad = "Short."
    gen = make_generator([bad, bad, bad])
    text = generate(gen)                       # ships it, the judge decides
    assert text == "Short."
    assert len(gen.chain.inputs) == gen.MAX_LINT_FIXES + 1


def test_judge_rejection_becomes_an_edit_of_the_last_draft():
    gen = make_generator([GOOD])
    generate(gen, previous_attempt="OLD DRAFT", revision_notes=["[example_quality] add a step"])
    block = gen.chain.inputs[0]["revision_block"]
    assert "OLD DRAFT" in block and "[example_quality] add a step" in block


def test_empty_output_raises():
    with pytest.raises(ValueError):
        generate(make_generator(["   "]))


def test_prompt_renders_with_every_variable_and_no_leftovers():
    from langchain_core.runnables import RunnableLambda
    from app.prompts.content_prompt import CONTENT_PROMPT

    gen = LessonContentGenerator.__new__(LessonContentGenerator)
    gen.chain = CONTENT_PROMPT | RunnableLambda(
        lambda value: "\n".join(m.content for m in value.to_messages()))

    rendered = gen._draft(
        topic="Acids", learner_profile="12th grade student", subtopic=sub(),
        previous_content="", source_facts=["A fact"], extra_rules=["A rule"],
        previous_attempt="OLD", notes=["fix it"])

    assert "Litmus paper turns red in acids" in rendered      # checklist
    assert "A fact" in rendered and "A rule" in rendered
    assert "REVISION: FIX YOUR PREVIOUS VERSION" in rendered
    for placeholder in ("{topic}", "{section_checklist}", "{revision_block}",
                        "{previous_content}", "{subtopic_title}"):
        assert placeholder not in rendered