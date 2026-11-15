"""Offline tests for the generate -> evaluate -> retry loop. No Zoho call."""

import json
from pathlib import Path

import pytest

from app.agents.evaluator import EvaluationError, TYPE_RULES
from app.agents.schemas import LessonEvaluation, LessonPlan
from app.memory.lesson_memory import LessonMemory
from app.workflow.lesson_workflow import LessonWorkflow

CRITERIA = ["accuracy", "required_coverage", "beginner_friendly",
            "simple_language", "jargon_explanation", "example_quality"]


def evaluation(failing=()):
    return LessonEvaluation.model_validate({"criteria": [
        {"criterion": c,
         "result": "FAIL" if c in failing else "PASS",
         "evidence": "quote",
         "feedback": "Fix this specific thing now." if c in failing else ""}
        for c in CRITERIA]})


def make_plan():
    def sub(i, t, builds):
        return {"id": f"S{i}", "title": f"Title {i}", "type": t,
                "must_teach": ["point"], "key_terms": ["term"],
                "example_idea": "idea", "builds_on": builds}
    return LessonPlan.model_validate({
        "topic": "Test Topic",
        "learning_outcomes": ["Explain A", "Describe B", "List C"],
        "prerequisite_terms": [],
        "subtopics": [sub(1, "foundation", []), sub(2, "core", ["S1"]),
                      sub(3, "application", ["S2"]), sub(4, "wrap-up", ["S3"])],
        "out_of_scope": ["advanced stuff"],
    })


class FakePlanner:
    def generate(self, **kwargs):
        return make_plan()


class FakeGenerator:
    def __init__(self):
        self.calls = []
        self.kwargs = []

    def generate_subtopic(self, subtopic, **kwargs):
        self.calls.append(subtopic.id)
        self.kwargs.append((subtopic.id, kwargs))
        n = self.calls.count(subtopic.id)
        return f"content {subtopic.id} v{n}"


class FakeEvaluator:
    """script: {subtopic_id: [verdict, verdict, ...]} where verdict is a
    list of failing criteria, or the string 'DOWN' for a judge outage."""

    def __init__(self, script=None):
        self.script = script or {}
        self.seen_previous = {}

    def evaluate(self, subtopic, previous_content="", **kwargs):
        self.seen_previous.setdefault(subtopic.id, previous_content)
        queue = self.script.get(subtopic.id)
        verdict = queue.pop(0) if queue else []
        if verdict == "DOWN":
            raise EvaluationError("judge down")
        return evaluation(verdict)


def build(tmp_path, script=None):
    wf = LessonWorkflow.__new__(LessonWorkflow)     # skip real Zoho setup
    wf.output_dir = Path(tmp_path)
    wf.planner = FakePlanner()
    wf.content_generator = FakeGenerator()
    wf.evaluator = FakeEvaluator(script)
    wf.memory = LessonMemory(memory_path=Path(tmp_path) / "memory.json")
    wf.last_run = None
    return wf


def run(wf):
    return wf.run(topic="Test Topic", learner_profile="12th grade student")


def test_all_pass_first_try(tmp_path):
    wf = build(tmp_path)
    lesson = run(wf)
    assert wf.last_run["status"] == "passed"
    assert wf.last_run["total_rejections"] == 0
    assert "QUALITY FLAG" not in lesson
    for i in range(1, 5):
        assert f"content S{i} v1" in lesson
    run_dir = Path(wf.last_run["output_dir"])
    assert (run_dir / "final_lesson.md").exists()
    assert (run_dir / "rejection_log.json").exists()
    assert (tmp_path / "lessons" / "test-topic.md").exists()


def test_retry_then_pass_is_logged(tmp_path):
    wf = build(tmp_path, {"S2": [["jargon_explanation"]]})
    lesson = run(wf)
    assert "content S2 v2" in lesson and "content S2 v1" not in lesson
    s2 = [s for s in wf.last_run["sections"] if s["id"] == "S2"][0]
    assert s2["status"] == "passed_after_retry" and s2["attempts"] == 2
    log = json.loads((Path(wf.last_run["output_dir"]) / "rejection_log.json").read_text())
    assert len(log) == 1
    assert log[0]["failed_criteria"] == ["jargon_explanation"]
    assert log[0]["retry_result"] == "PASSED"
    assert log[0]["changes_requested_on_retry"]
    assert wf.last_run["status"] == "passed"


def test_never_crashes_when_a_subtopic_always_fails(tmp_path):
    # attempt 1 fails 3 checks, attempt 2 fails 1 (best), attempt 3 fails 2
    script = {"S4": [["accuracy", "required_coverage", "example_quality"],
                     ["required_coverage"],
                     ["required_coverage", "example_quality"]]}
    wf = build(tmp_path, script)
    lesson = run(wf)                                  # must not raise
    assert wf.last_run["status"] == "needs_review"
    s4 = [s for s in wf.last_run["sections"] if s["id"] == "S4"][0]
    assert s4["status"] == "failed_max_retries" and s4["attempts"] == 3
    assert s4["failed_criteria"] == ["required_coverage"]
    assert "content S4 v2" in lesson                  # the BEST attempt shipped
    assert "QUALITY FLAG" in lesson and "S4" in lesson
    log = json.loads((Path(wf.last_run["output_dir"]) / "rejection_log.json").read_text())
    assert [e["attempt"] for e in log] == [1, 2, 3]
    assert log[0]["retry_result"].startswith("FAILED again")
    assert log[2]["retry_result"] == "no retry left"


def test_earlier_sections_are_kept_when_a_later_one_fails(tmp_path):
    wf = build(tmp_path, {"S4": [["accuracy"]] * 3})
    lesson = run(wf)
    for i in range(1, 4):
        assert f"content S{i} v1" in lesson


def test_judge_outage_ships_flagged_instead_of_crashing(tmp_path):
    wf = build(tmp_path, {"S3": ["DOWN"]})
    lesson = run(wf)
    s3 = [s for s in wf.last_run["sections"] if s["id"] == "S3"][0]
    assert s3["status"] == "judge_unavailable"
    assert wf.last_run["status"] == "needs_review"
    assert "content S3 v1" in lesson


def test_judge_sees_previous_sections(tmp_path):
    wf = build(tmp_path)
    run(wf)
    assert wf.evaluator.seen_previous["S1"] == ""
    assert "content S1 v1" in wf.evaluator.seen_previous["S2"]
    assert "content S3 v1" in wf.evaluator.seen_previous["S4"]


def test_no_duplicate_summary_sections(tmp_path):
    wf = build(tmp_path)
    lesson = run(wf)
    assert lesson.count("## Summary") == 0
    assert lesson.count("## What to learn next") == 0
    assert "## Introduction" in lesson and "- Explain A" in lesson


def test_wrap_up_has_its_own_rules():
    assert "recap" in TYPE_RULES["wrap-up"]
    assert set(TYPE_RULES) == {"foundation", "core", "application", "wrap-up"}


def test_retry_edits_the_last_draft_with_the_judges_reasons(tmp_path):
    wf = build(tmp_path, {"S2": [["jargon_explanation"]]})
    run(wf)
    s2_calls = [kw for sid, kw in wf.content_generator.kwargs if sid == "S2"]
    assert s2_calls[0]["previous_attempt"] is None
    assert s2_calls[1]["previous_attempt"] == "content S2 v1"
    assert s2_calls[1]["revision_notes"][0].startswith("[jargon_explanation]")


def test_judge_reasons_are_not_stored_as_permanent_rules(tmp_path):
    wf = build(tmp_path, {"S2": [["jargon_explanation"]]})
    run(wf)
    s2_calls = [kw for sid, kw in wf.content_generator.kwargs if sid == "S2"]
    assert not any("[jargon_explanation]" in r for r in s2_calls[1]["extra_rules"])


def test_first_try_pass_rate_is_reported(tmp_path):
    wf = build(tmp_path, {"S2": [["jargon_explanation"]]})
    run(wf)
    assert wf.last_run["first_try_pass_rate"] == 0.75   # 3 of 4 sections