from app.agents.generator import LessonPlanner
from app.agents.content_generator import LessonContentGenerator
import json
from pathlib import Path
from datetime import datetime, timezone

from app.agents.evaluator import LessonEvaluator
from app.memory.lesson_memory import LessonMemory


class LessonWorkflow:

    MAX_RETRIES = 2

    def __init__(self):
        self.planner = LessonPlanner()
        self.content_generator = LessonContentGenerator()
        self.evaluator = LessonEvaluator()
        self.memory = LessonMemory()

    def run(
    self,
    topic,
    learner_profile,
    lesson_minutes=20,
    min_subtopics=5,
    max_subtopics=8,
    source_facts=None,
    extra_rules=None, ):

        source_facts = source_facts or []
        extra_rules = extra_rules or []

    # ==========================================
    # STEP 1: GENERATE LESSON PLAN
    # ==========================================

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

    # ==========================================
    # STEP 2: GENERATE AND EVALUATE EACH SUBTOPIC
    # ==========================================

        print("\n========== STEP 2: CONTENT GENERATION ==========")

        generated_sections = []

        previous_content = ""

        for index, subtopic in enumerate(plan.subtopics, start=1):

            print(
            f"\nGenerating {index}/{len(plan.subtopics)}: "
            f"{subtopic.title}"
        )

            approved = False

            # Load previously learned rules for this topic.
            memory_rules = self.memory.get_rules(
            topic=topic,
            subtopic_type=subtopic.type,
            subtopic_title=subtopic.title
            )

            feedback_rules = list(
                dict.fromkeys(extra_rules + memory_rules)
            )

            print(f"Loaded {len(memory_rules)} rules from persistent memory.")

        # Initial attempt + maximum two retries
            for attempt in range(self.MAX_RETRIES + 1):

                print(f"\nGeneration attempt: {attempt + 1}")

            # --------------------------------------
            # 2A. GENERATE CONTENT
            # --------------------------------------

                content = self.content_generator.generate_subtopic(
                topic=topic,
                learner_profile=learner_profile,
                subtopic=subtopic,
                previous_content=previous_content,
                source_facts=source_facts,
                extra_rules=feedback_rules,
            )

                print("Content generated successfully.")

            # --------------------------------------
            # 2B. EVALUATE GENERATED CONTENT
            # --------------------------------------

                print("Evaluating generated content...")

                evaluation = self.evaluator.evaluate(
                topic=topic,
                learner_profile=learner_profile,
                subtopic=subtopic,
                generated_content=content,
                source_facts=source_facts,
            )

            # --------------------------------------
            # 2C. CHECK EVALUATION RESULT
            # --------------------------------------

                if evaluation.passed:

                    print("Evaluation: PASSED")

                    generated_sections.append({
                    "id": subtopic.id,
                    "title": subtopic.title,
                    "content": content,
                    "evaluation": evaluation.model_dump(),
                })

                # Only approved content becomes context
                # for subsequent subtopics.
                    previous_content += (
                    f"\n\n{subtopic.title}\n{content}"
                )

                    approved = True

                    print(f"Approved: {subtopic.id}")

                    break

            # --------------------------------------
            # 2D. HANDLE REJECTED CONTENT
            # --------------------------------------

                print("Evaluation: FAILED")

            # Preserve rejected content and feedback
                self.save_rejection(
                topic=topic,
                subtopic=subtopic,
                attempt=attempt + 1,
                content=content,
                evaluation=evaluation,
            )
                # Learn from failed evaluation criteria.
                self.memory.learn_from_evaluation(
                    topic=topic,
                    subtopic=subtopic,
                    evaluation=evaluation
                )

                print("Rejection log saved.")

            # Add evaluator feedback to the next
            # generation attempt.
                feedback_rules.extend(
                evaluation.revision_instructions
            )

                if attempt < self.MAX_RETRIES:

                    print(
                    "Regenerating content using "
                    "evaluator feedback..."
                )

        # --------------------------------------
        # 2E. STOP IF ALL ATTEMPTS FAIL
        # --------------------------------------

            if not approved:

                raise RuntimeError(
                f"Subtopic {subtopic.id} "
                f"({subtopic.title}) failed evaluation "
                f"after {self.MAX_RETRIES} retries."
            )

        print("\nALL SUBTOPICS GENERATED AND APPROVED")

    # ==========================================
    # STEP 3: ASSEMBLE COMPLETE LESSON
    # ==========================================

        print("\n========== STEP 3: LESSON ASSEMBLY ==========")

        lesson_parts = [
        f"# {topic}",
        "## Introduction",
        (
            f"By the end of this lesson, you will understand "
            f"{topic} and explain its basic working."
        ),
    ]

    # Add all approved sections in original plan order
        for section in generated_sections:

            lesson_parts.append(
            f"## {section['title']}\n\n"
            f"{section['content']}"
        )

    # Add lesson summary
        lesson_parts.append(
        "## Summary\n\n"
        + "\n".join(
            f"- {outcome}"
            for outcome in plan.learning_outcomes[:3]
        )
    )

    # Add next learning topics
        lesson_parts.append(
        "## What to learn next\n\n"
        + "\n".join(
            f"- {item}"
            for item in plan.out_of_scope[:2]
        )
    )

        final_lesson = "\n\n".join(lesson_parts)

    # ==========================================
    # STEP 4: RETURN FINAL LESSON
    # ==========================================

        print("\n========== LESSON COMPLETED ==========")

        print(f"Topic: {topic}")
        print(f"Approved sections: {len(generated_sections)}")
        print(f"Total characters: {len(final_lesson)}")

        return final_lesson

    def save_rejection(self, topic, subtopic, attempt, content, evaluation):
        log_path = Path("outputs/rejection_logs/rejections.jsonl")

        log_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
