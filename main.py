# from app.llm.zoho_quickml import ZohoQuickMLChat

# llm = ZohoQuickMLChat()

# response = llm.invoke("Explain RAG in simple English.")

# print("\nGenerated Response:")
# print(response.content)

# print("\nToken Usage:")
# print(response.usage_metadata)

# print("\nModel Information:")
# print(response.response_metadata)

# print("Test A — Multiple prompts")
# responses = llm.batch([
#     "What is RAG?",
#     "What is an LLM?",
#     "What is a vector database?"
# ])

# for response in responses:
#     print(response.content)
    
    
# print("Test B — Prompt template")
# from langchain_core.prompts import ChatPromptTemplate

# prompt = ChatPromptTemplate.from_messages([
#     ("system", "You are a beginner-friendly AI teacher."),
#     ("human", "Explain {topic} in simple English.")
# ])

# chain = prompt | llm

# response = chain.invoke({
#     "topic": "Retrieval-Augmented Generation"
# })

# print(response.content)



# print("Test C — Output parser")


# from langchain_core.output_parsers import StrOutputParser

# chain = prompt | llm | StrOutputParser()

# result = chain.invoke({
#     "topic": "Vector Database"
# })

# print(result)
    
    
    

# from app.agents.generator import LessonGenerator


# def main():

#     generator = LessonGenerator()

#     lesson = generator.generate(
#         topic="java programming"
#     )

#     print("\n========== GENERATED LESSON ==========\n")

#     print(lesson.model_dump_json(indent=2))


# if __name__ == "__main__":
#     main()





# from app.agents.generator import LessonPlanner


# def main():

#     planner = LessonPlanner()

#     plan = planner.generate(

#         topic="gravite",

#         learner_profile=(
#             "Indian 12th-grade student, "
#             "limited English vocabulary, "
#             "no technical background."
#         ),

#         lesson_minutes=20,

#         min_subtopics=5,

#         max_subtopics=8
#     )

#     print("\n========== LESSON PLAN ==========\n")

#     print(plan.model_dump_json(indent=2))


# if __name__ == "__main__":
#     main()





# from app.agents.generator import LessonPlanner

# from app.agents.content_generator import (
#     LessonContentGenerator
# )

# from app.agents.schemas import LessonContentRequest


# def main():

#     # STEP 1: Generate lesson plan
#     planner = LessonPlanner()

#     plan = planner.generate(

#         topic="Introduction to RAG",

#         learner_profile=(
#             "Indian 12th-grade student, "
#             "limited English vocabulary, "
#             "no technical background."
#         ),

#         lesson_minutes=20,

#         min_subtopics=5,

#         max_subtopics=8

#     )

#     print("\n========== LESSON PLAN GENERATED ==========\n")

#     print(plan.model_dump_json(indent=2))


#     # STEP 2: Prepare content generation request
#     request = LessonContentRequest(

#         topic="Introduction to RAG",

#         learner_profile=(
#             "Indian 12th-grade student, "
#             "limited English vocabulary, "
#             "no technical background."
#         ),

#         lesson_plan=plan,

#         source_facts=[
#             "RAG stands for Retrieval-Augmented Generation.",
#             "RAG retrieves relevant information before generating an answer.",
#             "RAG can reduce hallucinations but cannot eliminate them completely."
#         ],

#         extra_rules=[
#             "Never claim RAG guarantees correct answers.",
#             "Explain technical terms using simple language."
#         ],

#         word_count=800

#     )


#     # STEP 3: Generate actual lesson
#     content_generator = LessonContentGenerator()

#     lesson = content_generator.generate(request)


#     # STEP 4: Display lesson
#     print("\n========== GENERATED LESSON ==========\n")

#     print(lesson)


# if __name__ == "__main__":
#     main()


from app.workflow.lesson_workflow import LessonWorkflow


def main():

    workflow = LessonWorkflow()

    lesson = workflow.run(

        topic="Acids, Bases, and Salts",

        learner_profile=(
            "Indian 12th-grade student, "
            "limited English vocabulary, "
            "no technical background."
        ),

        lesson_minutes=50,

        min_subtopics=5,

        max_subtopics=8,

        source_facts=[
            # "RAG stands for Retrieval-Augmented Generation.",
            # "RAG retrieves relevant information before generating an answer.",
            # "RAG can reduce hallucinations but cannot eliminate them completely."
        ],

        extra_rules=[
            "Never claim RAG guarantees correct answers.",
            "Explain technical terms using simple language."
        ]
    )

    print("\n========== COMPLETE LESSON ==========\n")

    print(lesson)


if __name__ == "__main__":
    main()
