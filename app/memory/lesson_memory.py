
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

    
    MAX_RULES_PER_SUBTOPIC = 4

    def get_rules(
        self,
        topic,
        subtopic_type=None,
        subtopic_title=None,
    ):
        """Return a small, relevant set of previously learned rules.

        Exact subtopic matches rank first. Topic-level rules (records with no
        subtopic_title) rank after them. Rules from other subtopics are not
        mixed into the current prompt.
        """
        data = self._load()
        topic_key = self._normalize(topic)
        title_key = (
            self._normalize(subtopic_title)
            if subtopic_title else None
        )

        candidates = []

        for memory in data["memories"]:
            saved_topic = self._normalize(memory.get("topic", ""))
            if saved_topic not in {topic_key, "*"}:
                continue

            saved_type = memory.get("subtopic_type")
            if saved_type is not None and saved_type != subtopic_type:
                continue

            saved_title = memory.get("subtopic_title")
            if saved_title:
                if not title_key:
                    continue
                if self._normalize(saved_title) != title_key:
                    continue
                specificity = 2
            else:
                specificity = 1

            rule = str(memory.get("rule", "")).strip()
            if not rule:
                continue

            candidates.append((
                specificity,
                int(memory.get("occurrences", 1)),
                str(memory.get("last_seen", "")),
                rule,
            ))

        # Prefer exact-title rules, then repeatedly confirmed and recent rules.
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

        selected = []
        seen = set()
        for _, _, _, rule in candidates:
            normalized = self._normalize(rule)
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(rule)
            if len(selected) >= self.MAX_RULES_PER_SUBTOPIC:
                break

        return selected

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

                same_title = (
                    self._normalize(memory.get("subtopic_title", ""))
                    == self._normalize(subtopic.title)
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
                    and same_title
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
