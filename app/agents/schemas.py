from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator,
    computed_field,
)


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


CriterionName = Literal[
    "accuracy",
    "required_coverage",
    "beginner_friendly",
    "simple_language",
    "jargon_explanation",
    "example_quality"
]

REQUIRED_CRITERIA = frozenset(CriterionName.__args__)


class RubricCriterionResult(BaseModel):
    """One rubric check. Strictly PASS or FAIL. No scores, no partial credit."""

    # "ignore" so a stray field from the model (for example an old
    # "score" or "passed") does not crash the parser.
    model_config = ConfigDict(extra="ignore")

    criterion: CriterionName
    result: Literal["PASS", "FAIL"]
    evidence: str = Field(
        min_length=3,
        description="Short quote from the content that supports the verdict"
    )
    feedback: str = Field(
        default="",
        description="Required for FAIL: exactly what must change. Empty for PASS."
    )

    @model_validator(mode="after")
    def validate_feedback(self):
        # A FAIL without an actionable reason cannot be used on retry.
        if self.result == "FAIL" and len(self.feedback.strip()) < 10:
            raise ValueError(
                f"Criterion '{self.criterion}' failed but gave no "
                "specific feedback."
            )
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return self.result == "PASS"


class LessonEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    criteria: list[RubricCriterionResult]

    @model_validator(mode="before")
    @classmethod
    def merge_duplicate_criteria(cls, data):
        """
        The judge sometimes writes one entry per finding, so the same
        criterion can appear twice. Merge them in code: if ANY entry
        for a criterion is FAIL, the criterion is FAIL.
        """
        if not isinstance(data, dict):
            return data

        items = data.get("criteria")

        if not isinstance(items, list):
            return data

        groups = {}
        order = []

        for item in items:
            if not isinstance(item, dict) or "criterion" not in item:
                return data  # let normal validation report the problem

            name = item["criterion"]

            if name not in groups:
                groups[name] = []
                order.append(name)

            groups[name].append(item)

        merged = []

        for name in order:
            group = groups[name]

            failed = [
                g for g in group
                if str(g.get("result", "")).strip().upper() == "FAIL"
            ]

            evidence = " | ".join(dict.fromkeys(
                str(g.get("evidence", "")).strip()
                for g in group
                if str(g.get("evidence", "")).strip()
            ))

            feedback = " ".join(dict.fromkeys(
                str(g.get("feedback", "")).strip()
                for g in failed
                if str(g.get("feedback", "")).strip()
            ))

            merged.append({
                "criterion": name,
                "result": "FAIL" if failed else "PASS",
                "evidence": evidence,
                "feedback": feedback,
            })

        return {**data, "criteria": merged}

    @model_validator(mode="after")
    def validate_criteria(self):
        actual = {item.criterion for item in self.criteria}
        missing = sorted(REQUIRED_CRITERIA - actual)

        if missing:
            raise ValueError(
                f"Missing rubric criteria: {', '.join(missing)}. "
                "Give exactly one entry for each of the six criteria."
            )

        return self

    # The verdict is decided in code, never by the LLM.
    @computed_field
    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.criteria)

    @computed_field
    @property
    def failed_criteria(self) -> list[str]:
        return [item.criterion for item in self.criteria if not item.passed]

    # Built from the failed checks, so it can never disagree with them.
    @computed_field
    @property
    def revision_instructions(self) -> list[str]:
        return [
            f"[{item.criterion}] {item.feedback.strip()}"
            for item in self.criteria
            if not item.passed
        ]