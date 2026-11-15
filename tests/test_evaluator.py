"""Offline tests for the binary evaluator. No Zoho call is made."""

import json

import pytest
from langchain_core.messages import AIMessage

from app.agents import evaluator as evaluator_module
from app.agents.evaluator import EvaluationError, LessonEvaluator
from app.agents.schemas import LessonEvaluation, LessonSubtopic
from app.memory.lesson_memory import LessonMemory

CRITERIA = [
    "accuracy",
    "required_coverage",
    "beginner_friendly",
    "simple_language",
    "jargon_explanation",
    "example_quality",
]


def make_json(failing=None, feedback="Add a clear everyday example now."):
    failing = failing or []
    items = []
    for name in CRITERIA:
        if name in failing:
            items.append({"criterion": name, "result": "FAIL",
                          "evidence": "Not found in content", "feedback": feedback})
        else:
            items.append({"criterion": name, "result": "PASS",
                          "evidence": "a short quote", "feedback": ""})
    return json.dumps({"criteria": items})


class FakeLLM:
    """Returns scripted replies. An Exception in the list is raised."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.last_messages = None

    def invoke(self, messages):
        self.calls += 1
        self.last_messages = messages
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return AIMessage(content=reply)


@pytest.fixture
def subtopic():
    return LessonSubtopic(
        id="S1", title="What is RAG?", type="foundation",
        must_teach=["RAG gives an AI extra information before it answers"],
        key_terms=["RAG"], example_idea="Open-book exam", builds_on=[],
    )


def run(replies, subtopic):
    judge = LessonEvaluator.__new__(LessonEvaluator)   # skip Zoho __init__
    judge.llm = FakeLLM(replies)
    judge.RETRY_DELAY_SECONDS = 0
    result = judge.evaluate("RAG", "12th grade student", subtopic, "lesson text", [])
    return result, judge.llm.calls


def test_all_pass(subtopic):
    result, calls = run([make_json()], subtopic)
    assert result.passed is True
    assert result.revision_instructions == []
    assert calls == 1


def test_single_fail_fails_whole_lesson(subtopic):
    result, _ = run([make_json(failing=["jargon_explanation"])], subtopic)
    assert result.passed is False
    assert result.failed_criteria == ["jargon_explanation"]
    assert result.revision_instructions[0].startswith("[jargon_explanation]")


def test_old_score_style_output_is_retried(subtopic):
    old_style = json.dumps({"criteria": [
        {"criterion": c, "score": 3, "passed": False, "evidence": "x", "feedback": "y"}
        for c in CRITERIA]})
    result, calls = run([old_style, make_json()], subtopic)
    assert result.passed is True
    assert calls == 2


def test_fail_without_feedback_is_retried(subtopic):
    bad = make_json(failing=["accuracy"], feedback="")
    result, calls = run([bad, make_json(failing=["accuracy"])], subtopic)
    assert result.failed_criteria == ["accuracy"]
    assert calls == 2


def test_missing_criterion_is_retried(subtopic):
    data = json.loads(make_json())
    data["criteria"].pop()
    result, calls = run([json.dumps(data), make_json()], subtopic)
    assert result.passed is True and calls == 2


def test_api_errors_are_retried(subtopic):
    result, calls = run(
        [RuntimeError("timeout"), RuntimeError("timeout"), make_json()], subtopic)
    assert result.passed is True and calls == 3


def test_gives_up_after_max_attempts(subtopic):
    with pytest.raises(EvaluationError):
        run(["not json", "still not json", "nope"], subtopic)


def test_think_block_and_code_fence_are_handled(subtopic):
    wrapped = "<think>let me check</think>\n```json\n" + make_json() + "\n```"
    result, calls = run([wrapped], subtopic)
    assert result.passed is True and calls == 1


def test_log_dump_contains_verdict_fields(subtopic):
    result, _ = run([make_json(failing=["example_quality"])], subtopic)
    dump = result.model_dump()
    assert dump["passed"] is False
    assert dump["failed_criteria"] == ["example_quality"]
    assert dump["revision_instructions"]


def test_memory_still_works_with_new_schema(subtopic, tmp_path):
    result, _ = run([make_json(failing=["jargon_explanation"])], subtopic)
    memory = LessonMemory(memory_path=tmp_path / "memory.json")
    memory.learn_from_evaluation("RAG", subtopic, result)
    assert memory.get_rules("RAG", subtopic_type="foundation",
                            subtopic_title="What is RAG?")


# ---- Real judge output that crashed a run: one entry per finding ----
DUPLICATED_OUTPUT = json.dumps({"criteria": [
    {"criterion": "accuracy", "result": "PASS", "evidence": "A salt is formed when an acid and a base react.", "feedback": ""},
    {"criterion": "required_coverage", "result": "PASS", "evidence": "Table salt (sodium chloride) is a common salt.", "feedback": ""},
    {"criterion": "required_coverage", "result": "PASS", "evidence": "Salts are used in food and industry.", "feedback": ""},
    {"criterion": "beginner_friendly", "result": "PASS", "evidence": "The acid and the base cancel each other out.", "feedback": ""},
    {"criterion": "simple_language", "result": "PASS", "evidence": "It is a white, solid powder.", "feedback": ""},
    {"criterion": "simple_language", "result": "PASS", "evidence": "We add salt to food to make it taste better.", "feedback": ""},
    {"criterion": "jargon_explanation", "result": "FAIL", "evidence": "The reaction is called neutralization.", "feedback": "Explain the term 'neutralization' in simple words."},
    {"criterion": "jargon_explanation", "result": "FAIL", "evidence": "They react to make bubbles and a salt solution.", "feedback": "Explain the term 'salt solution' in simple words."},
    {"criterion": "example_quality", "result": "PASS", "evidence": "We mix vinegar (an acid) and baking soda (a base).", "feedback": ""},
]})


def test_duplicate_entries_are_merged_not_rejected(subtopic):
    result, calls = run([DUPLICATED_OUTPUT], subtopic)
    assert calls == 1                      # no retry needed
    assert len(result.criteria) == 6
    assert result.passed is False
    assert result.failed_criteria == ["jargon_explanation"]
    # both findings are kept in the single merged feedback
    text = result.revision_instructions[0]
    assert "neutralization" in text and "salt solution" in text


def test_pass_and_fail_for_same_criterion_means_fail(subtopic):
    data = json.loads(make_json())
    data["criteria"].append({"criterion": "accuracy", "result": "FAIL",
                             "evidence": "wrong claim here",
                             "feedback": "Remove the wrong claim about acids."})
    result, _ = run([json.dumps(data)], subtopic)
    assert result.failed_criteria == ["accuracy"]
    assert len(result.criteria) == 6


def test_missing_criterion_error_names_it(subtopic):
    data = json.loads(make_json())
    data["criteria"] = [c for c in data["criteria"] if c["criterion"] != "accuracy"]
    with pytest.raises(Exception) as info:
        LessonEvaluation.model_validate(data)
    assert "accuracy" in str(info.value)


def test_prompt_contains_previous_content_and_wrap_up_rules():
    wrap = LessonSubtopic(
        id="S5", title="Summary", type="wrap-up",
        must_teach=["recap the idea"], key_terms=["RAG"],
        example_idea="Open-book exam", builds_on=[],
    )
    judge = LessonEvaluator.__new__(LessonEvaluator)
    judge.llm = FakeLLM([make_json()])
    judge.RETRY_DELAY_SECONDS = 0
    judge.evaluate("RAG", "student", wrap, "recap text", [],
                   previous_content="EARLIER SECTION TEXT")
    prompt = judge.llm.last_messages[0].content
    assert "EARLIER SECTION TEXT" in prompt
    assert "recap, not new teaching" in prompt


def test_first_section_says_no_previous_content(subtopic):
    judge = LessonEvaluator.__new__(LessonEvaluator)
    judge.llm = FakeLLM([make_json()])
    judge.RETRY_DELAY_SECONDS = 0
    judge.evaluate("RAG", "student", subtopic, "text", [])
    assert "first section" in judge.llm.last_messages[0].content