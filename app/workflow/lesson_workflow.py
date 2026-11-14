
from app.agents.generator import LessonPlanner
from app.agents.content_generator import LessonContentGenerator


class LessonWorkflow:

    def __init__(self):

        self.planner = LessonPlanner()

        self.content_generator = LessonContentGenerator()

    def run(
        self,
        topic,
        learner_profile,
        lesson_minutes=20,
        min_subtopics=5,
        max_subtopics=8,
        source_facts=None,
        extra_rules=None
    ):

        source_facts = source_facts or []
        extra_rules = extra_rules or []

        # STEP 1: Generate lesson plan
        plan = self.planner.generate(

            topic=topic,

            learner_profile=learner_profile,

            lesson_minutes=lesson_minutes,

            min_subtopics=min_subtopics,

            max_subtopics=max_subtopics

        )

        print("\nLESSON PLAN CREATED")

        generated_sections = []

        previous_content = ""

        # STEP 2: Generate one subtopic at a time
        for index, subtopic in enumerate(plan.subtopics, start=1):

            print(
                f"\nGenerating {index}/{len(plan.subtopics)}: "
                f"{subtopic.title}"
            )

            content = self.content_generator.generate_subtopic(

                topic=topic,

                learner_profile=learner_profile,

                subtopic=subtopic,

                previous_content=previous_content,

                source_facts=source_facts,

                extra_rules=extra_rules

            )

            generated_sections.append({
                "id": subtopic.id,
                "title": subtopic.title,
                "content": content
            })

            # Give later sections the earlier teaching context.
            previous_content += (
                f"\n\n{subtopic.title}\n{content}"
            )

            print(f"Completed: {subtopic.id}")

        # STEP 3: Combine all sections in original order
        lesson_parts = [
            f"# {topic}",
            "## Introduction",
            f"By the end of this lesson, you will understand {topic} "
            "and explain its basic working."
        ]

        for section in generated_sections:

            lesson_parts.append(
                f"\n## {section['title']}\n\n"
                f"{section['content']}"
            )

        lesson_parts.append(
            "\n## Summary\n\n"
            + "\n".join(
                f"- {outcome}"
                for outcome in plan.learning_outcomes[:3]
            )
        )

        lesson_parts.append(
            "\n## What to learn next\n\n"
            + "\n".join(
                f"- {item}" for item in plan.out_of_scope[:2]
            )
        )

        return "\n\n".join(lesson_parts)
