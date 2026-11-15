
import json
import re

from pathlib import Path
from datetime import datetime, timezone


class LessonMemory:

    def __init__(self, memory_path=None):

        self.memory_path = (
            Path(memory_path)
            if memory_path
            else Path("outputs/memory/lesson_memory.json")
        )

        self.memory_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not self.memory_path.exists():
            self._save({
                "version": 1,
                "memories": []
            })

    def _load(self):

        try:
            with self.memory_path.open(
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError("Memory file must contain a JSON object.")

            if not isinstance(data.get("memories"), list):
                raise ValueError("Memory file has an invalid memories list.")

            return data

        except (json.JSONDecodeError, OSError, ValueError) as error:

            raise RuntimeError(
                f"Could not load lesson memory: {error}"
            ) from error

    def _save(self, data):

        temp_path = self.memory_path.with_suffix(".tmp")

        with temp_path.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )

        temp_path.replace(self.memory_path)

    @staticmethod
    def _normalize(text):

        return re.sub(
            r"\s+",
            " ",
            text.strip().lower()
        )

    
    def get_rules(
    self,
    topic,
    subtopic_type=None,
    subtopic_title=None
    ):

        data = self._load()

        topic_key = self._normalize(topic)

        relevant_rules = []

        for memory in data["memories"]:

            saved_topic_key = self._normalize(
            memory.get("topic", "")
            )

            # Match the same topic or global rules.
            topic_matches = (
            saved_topic_key == topic_key
            or saved_topic_key == "*"
            )

            if not topic_matches:
                continue

            saved_type = memory.get("subtopic_type")

            type_matches = (
            saved_type is None
            or saved_type == subtopic_type
            )

            if not type_matches:
                continue

            saved_title = memory.get("subtopic_title")

            # Title-specific memories should only be used
            # for the same subtopic.
            if saved_title and subtopic_title:

                title_matches = (
                self._normalize(saved_title)
                == self._normalize(subtopic_title)
                )

                if not title_matches:
                    continue

            elif saved_title and not subtopic_title:

            # Do not apply title-specific memory
            # when no target title is provided.
                continue

            relevant_rules.append(memory["rule"])

        return list(dict.fromkeys(relevant_rules))

    def learn_from_evaluation(
        self,
        topic,
        subtopic,
        evaluation
    ):

        data = self._load()

        memories = data["memories"]

        for criterion in evaluation.criteria:

            # Learn only from failed criteria.
            if criterion.passed:
                continue

            rule = criterion.feedback.strip()

            if not rule:
                continue

            topic_key = self._normalize(topic)
            rule_key = self._normalize(rule)

            existing_memory = None

            for memory in memories:

                same_topic = (
                    self._normalize(memory["topic"])
                    == topic_key
                )

                same_type = (
                    memory.get("subtopic_type")
                    == subtopic.type
                )

                same_criterion = (
                    memory["criterion"]
                    == criterion.criterion
                )

                same_rule = (
                    self._normalize(memory["rule"])
                    == rule_key
                )

                if (
                    same_topic
                    and same_type
                    and same_criterion
                    and same_rule
                ):

                    existing_memory = memory
                    break

            if existing_memory:

                # Update existing memory instead of
                # storing duplicate feedback.
                existing_memory["occurrences"] += 1

                existing_memory["last_seen"] = (
                    datetime.now(timezone.utc).isoformat()
                )

            else:

                memories.append({

                    "topic": topic,

                    "subtopic_type": subtopic.type,

                    "subtopic_title": subtopic.title,

                    "criterion": criterion.criterion,

                    "rule": rule,

                    "occurrences": 1,

                    "created_at": (
                        datetime.now(timezone.utc).isoformat()
                    ),

                    "last_seen": (
                        datetime.now(timezone.utc).isoformat()
                    )
                })

        self._save(data)

        print("Persistent memory updated.")
