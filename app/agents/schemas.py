
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator


class LessonSubtopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique subtopic ID, such as S1")
    title: str = Field(description="Clear title of the subtopic")

    type: Literal[
        "foundation",
        "core",
        "application",
        "wrap-up"
    ]

    must_teach: list[str] = Field(
        min_length=1,
        description="Key points the learner must understand"
    )

    key_terms: list[str] = Field(
        description="Terms that must be defined in this subtopic"
    )

    example_idea: str = Field(
        description="Simple everyday example or analogy"
    )

    builds_on: list[str] = Field(
        description="IDs of earlier subtopics this depends on"
    )


class LessonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="Requested lesson topic")

    learning_outcomes: list[str] = Field(
        min_length=3,
        description="Skills the learner should gain"
    )

    prerequisite_terms: list[str] = Field(
        description="Prerequisite terms or ideas"
    )

    subtopics: list[LessonSubtopic] = Field(
        min_length=3,
        description="Ordered list of lesson subtopics"
    )

    out_of_scope: list[str] = Field(
        description="Advanced concepts deliberately excluded"
    )

    @model_validator(mode="after")
    def validate_subtopics(self):

        ids = [item.id for item in self.subtopics]

        if len(ids) != len(set(ids)):
            raise ValueError("Subtopic IDs must be unique")

        available_ids = set()

        for item in self.subtopics:

            if item.id in item.builds_on:
                raise ValueError(
                    f"{item.id} cannot depend on itself"
                )

            for dependency in item.builds_on:
                if dependency not in available_ids:
                    raise ValueError(
                        f"{item.id} depends on {dependency}, "
                        "which must appear earlier"
                    )

            available_ids.add(item.id)

        types = [item.type for item in self.subtopics]

        if "foundation" not in types:
            raise ValueError("At least one foundation subtopic required")

        if "core" not in types:
            raise ValueError("At least one core subtopic required")

        if "application" not in types:
            raise ValueError("At least one application subtopic required")

        if "wrap-up" not in types:
            raise ValueError("At least one wrap-up subtopic required")

        return self
    
    
    
    
    
from pydantic import BaseModel, Field, ConfigDict

# Import your existing LessonPlan class if this is a separate file.
# from app.agents.schemas import LessonPlan


class LessonContentRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(
        min_length=2,
        description="Topic of the lesson"
    )

    learner_profile: str = Field(
        min_length=5,
        description="Description of the target learner"
    )

    lesson_plan: LessonPlan = Field(
        description="Approved lesson plan"
    )

    source_facts: list[str] = Field(
        default_factory=list,
        description="Verified facts the lesson must follow"
    )

    extra_rules: list[str] = Field(
        default_factory=list,
        description="Additional rules learned from previous failures"
    )

    word_count: int = Field(
        default=800,
        ge=200,
        le=3000
    )
    
    
    
    

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


CriterionName = Literal[
    "accuracy",
    "required_coverage",
    "beginner_friendly",
    "simple_language",
    "jargon_explanation",
    "example_quality"
]


class RubricCriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: CriterionName
    score: int = Field(ge=1, le=5)
    passed: bool
    evidence: str
    feedback: str

    @model_validator(mode="after")
    def validate_score(self):
        if self.passed != (self.score >= 4):
            raise ValueError(
                "A criterion passes only when its score is 4 or 5."
            )
        return self


class LessonEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterionResult] = Field(min_length=6)
    revision_instructions: list[str]

    @model_validator(mode="after")
    def validate_criteria(self):
        expected = {
            "accuracy",
            "required_coverage",
            "beginner_friendly",
            "simple_language",
            "jargon_explanation",
            "example_quality"
        }

        actual = {item.criterion for item in self.criteria}

        if actual != expected or len(self.criteria) != 6:
            raise ValueError(
                "All six rubric criteria must appear exactly once."
            )

        return self

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.criteria)


