
from app.llm.zoho_quickml import ZohoQuickMLChat
from app.prompts.evaluator_prompt import (
    EVALUATOR_PROMPT,
    parser
)


class LessonEvaluator:

    def __init__(self):
        self.llm = ZohoQuickMLChat()

        self.chain = (
            EVALUATOR_PROMPT
            | self.llm
            | parser
        )

    def evaluate(
        self,
        topic,
        learner_profile,
        subtopic,
        generated_content,
        source_facts
    ):

        result = self.chain.invoke({

            "topic": topic,

            "learner_profile": learner_profile,

            "subtopic_json": subtopic.model_dump_json(
                indent=2
            ),

            "generated_content": generated_content,

            "source_facts": "\n".join(
                f"- {fact}" for fact in source_facts
            ),

            "format_instructions": parser.get_format_instructions()
        })

        return result
