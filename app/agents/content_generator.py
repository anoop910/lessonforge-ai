
from langchain_core.output_parsers import StrOutputParser

from app.llm.zoho_quickml import ZohoQuickMLChat
from app.prompts.content_prompt import CONTENT_PROMPT


class LessonContentGenerator:

    def __init__(self):
        self.llm = ZohoQuickMLChat()

        self.chain = (
            CONTENT_PROMPT
            | self.llm
            | StrOutputParser()
        )

    def generate_subtopic(
        self,
        topic,
        learner_profile,
        subtopic,
        previous_content,
        source_facts,
        extra_rules
    ):

        response = self.chain.invoke({

            "topic": topic,

            "learner_profile": learner_profile,

            "subtopic_json": subtopic.model_dump_json(indent=2),

            "subtopic_title": subtopic.title,

            "previous_content": previous_content,

            "source_facts": "\n".join(
                f"- {fact}" for fact in source_facts
            ),

            "extra_rules": "\n".join(
                f"- {rule}" for rule in extra_rules
            )

        })

        if not response.strip():
            raise ValueError(
                f"Empty content generated for {subtopic.id}"
            )

        return response.strip()
