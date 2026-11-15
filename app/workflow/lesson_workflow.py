import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.agents.content_generator import LessonContentGenerator
from app.agents.evaluator import EvaluationError, LessonEvaluator
from app.agents.generator import LessonPlanner
from app.memory.lesson_memory import LessonMemory


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "lesson"


class LessonWorkflow:

    # First attempt + up to 2 retries per subtopic. The loop always ends.
    MAX_RETRIES = 2

    # Section statuses that count as "cleared the quality bar".
    OK_STATUSES = ("passed", "passed_after_retry")

    # Keep dependency context bounded so prompts do not grow with every section.
    MAX_DEPENDENCY_SECTION_CHARS = 550
    MAX_DEPENDENCY_CONTEXT_CHARS = 3200

    def __init__(self, output_dir="outputs"):
        self.output_dir = Path(output_dir)
        self.planner = LessonPlanner()
        self.content_generator = LessonContentGenerator()
        self.evaluator = LessonEvaluator()
        self.memory = LessonMemory()

        # Summary of the most recent run (also saved to run_summary.json).
        self.last_run = None

    # ==========================================
    # MAIN ENTRY POINT
    # ==========================================

    def run(
        self,
        topic,
        learner_profile,
        lesson_minutes=20,
        min_subtopics=5,
        max_subtopics=8,
        source_facts=None,
        extra_rules=None,
    ):

        source_facts = source_facts or []
        extra_rules = extra_rules or []

        run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slug(topic)}"
        run_dir = self.output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # ---------- STEP 1: PLAN ----------
        print("\n========== STEP 1: LESSON PLANNING ==========")

        plan = self.planner.generate(
            topic=topic,
            learner_profile=learner_profile,
            lesson_minutes=lesson_minutes,
            min_subtopics=min_subtopics,
            max_subtopics=max_subtopics,
        )

        print("\nLESSON PLAN CREATED SUCCESSFULLY")
        print(f"Topic: {plan.topic}")
        print(f"Total subtopics: {len(plan.subtopics)}")

        # ---------- STEP 2: GENERATE + EVALUATE EACH SUBTOPIC ----------
        print("\n========== STEP 2: CONTENT GENERATION ==========")

        sections = []
        section_status = []
        rejection_log = []
        section_context_by_id = {}

        for index, subtopic in enumerate(plan.subtopics, start=1):

            print(
                f"\nGenerating {index}/{len(plan.subtopics)}: "
                f"{subtopic.title}"
            )

            # Only pass sections explicitly listed in builds_on. This avoids
            # sending the entire growing lesson to every model call.
            previous_content = self._build_dependency_context(
                subtopic.builds_on,
                section_context_by_id,
            )

            content, status = self._process_subtopic(
                run_id=run_id,
                topic=topic,
                learner_profile=learner_profile,
                subtopic=subtopic,
                previous_content=previous_content,
                source_facts=source_facts,
                extra_rules=extra_rules,
                rejection_log=rejection_log,
            )

            sections.append({
                "id": subtopic.id,
                "title": subtopic.title,
                "content": content,
            })
            section_status.append(status)

            # Keep this section available to later subtopics that explicitly
            # depend on it. A failed section remains available but the final
            # lesson status is still marked needs_review.
            section_context_by_id[subtopic.id] = {
                "title": subtopic.title,
                "content": content,
            }

        flagged = [
            item for item in section_status
            if item["status"] not in self.OK_STATUSES
        ]

        # ---------- STEP 3: ASSEMBLE ----------
        print("\n========== STEP 3: LESSON ASSEMBLY ==========")

        final_lesson = self._assemble(topic, plan, sections, flagged)

        # ---------- STEP 4: SAVE OUTPUTS ----------
        overall = "needs_review" if flagged else "passed"

        summary = {
            "run_id": run_id,
            "topic": topic,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": overall,
            "max_retries_per_subtopic": self.MAX_RETRIES,
            "sections": section_status,
            "total_rejections": len(rejection_log),
            "first_try_pass_rate": round(
                sum(
                    1 for item in section_status
                    if item["status"] == "passed"
                ) / max(len(section_status), 1),
                2,
            ),
        }

        lesson_path = run_dir / "final_lesson.md"
        lesson_path.write_text(final_lesson, encoding="utf-8")

        (run_dir / "rejection_log.json").write_text(
            json.dumps(rejection_log, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (run_dir / "run_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        latest_dir = self.output_dir / "lessons"
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / f"{_slug(topic)}.md").write_text(
            final_lesson, encoding="utf-8"
        )

        summary["output_dir"] = str(run_dir)
        self.last_run = summary

        print("\n========== LESSON COMPLETED ==========")
        print(f"Topic: {topic}")
        print(f"Status: {overall.upper()}")
        print(f"Sections: {len(sections)}  |  Rejections: {len(rejection_log)}")
        print(f"First-try pass rate: {summary['first_try_pass_rate']:.0%}")
        print(f"Saved to: {run_dir}")

        if flagged:
            print("\nWARNING: these sections did NOT pass the rubric:")
            for item in flagged:
                print(
                    f"  - {item['id']} {item['title']}: {item['status']} "
                    f"({', '.join(item['failed_criteria']) or 'n/a'})"
                )

        return final_lesson

    def _build_dependency_context(self, dependency_ids, sections_by_id):
        """Build a compact context from only the declared prerequisites."""
        parts = []

        for dependency_id in dependency_ids:
            section = sections_by_id.get(dependency_id)
            if not section:
                continue

            excerpt = section["content"].strip()
            if len(excerpt) > self.MAX_DEPENDENCY_SECTION_CHARS:
                excerpt = excerpt[:self.MAX_DEPENDENCY_SECTION_CHARS].rsplit(
                    " ", 1
                )[0] + " ...[section excerpt]"

            parts.append(f"## {section['title']}\n{excerpt}")

        context = "\n\n".join(parts)
        if len(context) > self.MAX_DEPENDENCY_CONTEXT_CHARS:
            context = context[:self.MAX_DEPENDENCY_CONTEXT_CHARS].rsplit(
                " ", 1
            )[0] + " ...[dependency context shortened]"

        return context

    # ==========================================
    # ONE SUBTOPIC: GENERATE -> EVALUATE -> RETRY
    # ==========================================

    def _process_subtopic(
        self,
        run_id,
        topic,
        learner_profile,
        subtopic,
        previous_content,
        source_facts,
        extra_rules,
        rejection_log,
    ):

        memory_rules = self.memory.get_rules(
            topic=topic,
            subtopic_type=subtopic.type,
            subtopic_title=subtopic.title,
        )

        feedback_rules = list(dict.fromkeys(extra_rules + memory_rules))

        print(f"Loaded {len(memory_rules)} rules from persistent memory.")

        best = None              # (failed_count, content, evaluation)
        last_rejection = None    # log entry waiting for its retry result
        previous_attempt = None  # last rejected draft (edited on retry)
        revision_notes = None    # the judge's reasons for rejecting it
        final_content = None
        final_eval = None
        status = "failed_max_retries"
        attempts_used = 0

        for attempt in range(1, self.MAX_RETRIES + 2):

            attempts_used = attempt
            print(f"\nGeneration attempt: {attempt}")

            content = self.content_generator.generate_subtopic(
                topic=topic,
                learner_profile=learner_profile,
                subtopic=subtopic,
                previous_content=previous_content,
                source_facts=source_facts,
                extra_rules=feedback_rules,
                previous_attempt=previous_attempt,
                revision_notes=revision_notes,
            )

            print("Content generated successfully.")
            print("Evaluating generated content...")

            try:
                evaluation = self.evaluator.evaluate(
                    topic=topic,
                    learner_profile=learner_profile,
                    subtopic=subtopic,
                    generated_content=content,
                    source_facts=source_facts,
                    previous_content=previous_content,
                )

            except EvaluationError as error:
                # The judge is down. Retrying generation will not help,
                # so ship this attempt and flag it instead of crashing.
                print(f"Judge unavailable: {error}")

                if last_rejection is not None:
                    last_rejection["retry_result"] = "judge unavailable"

                status = "judge_unavailable"
                final_content = content
                break

            # Close the previous rejection: did the retry fix it?
            if last_rejection is not None:
                last_rejection["retry_result"] = (
                    "PASSED"
                    if evaluation.passed
                    else "FAILED again: "
                    + ", ".join(evaluation.failed_criteria)
                )
                last_rejection["words_after_retry"] = len(content.split())
                last_rejection = None

            if evaluation.passed:

                print("Evaluation: PASSED")
                print(f"Approved: {subtopic.id}")

                status = "passed" if attempt == 1 else "passed_after_retry"
                final_content = content
                final_eval = evaluation
                break

            # ---- rejected ----
            print(
                "Evaluation: FAILED "
                f"({', '.join(evaluation.failed_criteria)})"
            )

            record = {
                "run_id": run_id,
                "subtopic_id": subtopic.id,
                "subtopic_title": subtopic.title,
                "attempt": attempt,
                "failed_criteria": evaluation.failed_criteria,
                "reasons": evaluation.revision_instructions,
                "changes_requested_on_retry": evaluation.revision_instructions,
                "words_before_retry": len(content.split()),
                "retry_result": "no retry left",
                "rejected_content": content,
            }
            rejection_log.append(record)
            last_rejection = record

            self.save_rejection(
                topic=topic,
                subtopic=subtopic,
                attempt=attempt,
                content=content,
                evaluation=evaluation,
                run_id=run_id,
            )

            self.memory.learn_from_evaluation(
                topic=topic,
                subtopic=subtopic,
                evaluation=evaluation,
            )

            print("Rejection log saved.")

            previous_attempt = content
            revision_notes = list(evaluation.revision_instructions)

            failed_count = len(evaluation.failed_criteria)

            if best is None or failed_count <= best[0]:
                best = (failed_count, content, evaluation)

            if attempt <= self.MAX_RETRIES:
                print("Regenerating content using evaluator feedback...")

        # ---- out of retries: ship the best attempt, flagged ----
        if status == "failed_max_retries":
            _, final_content, final_eval = best
            print(
                f"\nWARNING: {subtopic.id} did not pass after "
                f"{self.MAX_RETRIES} retries. Shipping the best attempt "
                "and flagging it for review."
            )

        failed_criteria = (
            final_eval.failed_criteria if final_eval is not None else []
        )

        return final_content, {
            "id": subtopic.id,
            "title": subtopic.title,
            "status": status,
            "attempts": attempts_used,
            "failed_criteria": failed_criteria,
        }

    # ==========================================
    # ASSEMBLY
    # ==========================================

    def _assemble(self, topic, plan, sections, flagged):

        parts = [f"# {topic}"]

        if flagged:
            ids = ", ".join(item["id"] for item in flagged)
            parts.append(
                "<!-- QUALITY FLAG: section(s) "
                f"{ids} did not pass the rubric. Human review needed. -->"
            )

        # The plan always has a wrap-up subtopic (the schema enforces it),
        # so the lesson already ends with a summary and next steps.
        parts.append(
            "## Introduction\n\n"
            "In this lesson, you will learn to:\n\n"
            + "\n".join(f"- {outcome}" for outcome in plan.learning_outcomes)
        )

        for section in sections:
            parts.append(f"## {section['title']}\n\n{section['content']}")

        return "\n\n".join(parts) + "\n"

    # ==========================================
    # GLOBAL REJECTION LOG (all runs, one line each)
    # ==========================================

    def save_rejection(
        self,
        topic,
        subtopic,
        attempt,
        content,
        evaluation,
        run_id=None,
    ):
        log_path = self.output_dir / "rejection_logs" / "rejections.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "topic": topic,
            "subtopic_id": subtopic.id,
            "subtopic_title": subtopic.title,
            "attempt": attempt,
            "generated_content": content,
            "evaluation": evaluation.model_dump(),
            "revision_instructions": evaluation.revision_instructions,
        }

        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")