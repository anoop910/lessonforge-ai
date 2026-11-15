from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TutorMode = Literal["chat", "explain", "example"]


class CreateTutorChatRequest(BaseModel):
    lesson_title: str = Field(min_length=2, max_length=200)
    lesson_content: str = Field(min_length=20, max_length=30000)


class CreateTutorChatResponse(BaseModel):
    chat_id: str
    lesson_title: str
    created_at: str


class SendTutorMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    mode: TutorMode = "chat"


class TutorMessageResponse(BaseModel):
    chat_id: str
    answer: str
    mode: TutorMode
    created_at: str


class TutorMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    mode: str | None = None
    created_at: str


class TutorHistoryResponse(BaseModel):
    chat_id: str
    lesson_title: str
    messages: list[TutorMessageItem]


class TutorChatListItem(BaseModel):
    chat_id: str
    lesson_title: str
    created_at: str
    updated_at: str


class QuizOption(BaseModel):
    id: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1, max_length=300)


class GeneratedQuiz(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    options: list[QuizOption] = Field(min_length=4, max_length=4)
    correct_option: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def validate_options(self):
        ids = [option.id for option in self.options]
        if ids != ["A", "B", "C", "D"]:
            raise ValueError("Quiz options must be ordered A, B, C, D.")
        return self


class TutorQuizResponse(BaseModel):
    chat_id: str
    question: str
    options: list[QuizOption]


class SubmitQuizAnswerRequest(BaseModel):
    option_id: Literal["A", "B", "C", "D"]


class QuizAnswerResponse(BaseModel):
    chat_id: str
    correct: bool
    selected_option: str
    correct_option: str
    explanation: str
    feedback: str
