from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import streamlit as st


# Make project imports work when Streamlit is launched from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RUNS_DIR = OUTPUTS_DIR / "runs"
LESSONS_DIR = OUTPUTS_DIR / "lessons"
MEMORY_FILE = OUTPUTS_DIR / "memory" / "lesson_memory.json"
GLOBAL_REJECTIONS_FILE = OUTPUTS_DIR / "rejection_logs" / "rejections.jsonl"

st.set_page_config(
    page_title="LessonForge AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1450px;}
      [data-testid="stMetric"] {background: rgba(120,120,120,.07); padding: 14px 16px; border-radius: 12px;}
      .lf-muted {color: #8b949e; font-size: .9rem;}
      .lf-pill {display:inline-block; padding:3px 9px; border-radius:999px; font-size:.78rem; background:rgba(120,120,120,.13);}
      div[data-testid="stChatMessage"] {border-radius: 12px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _load_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return runs
    for summary_path in RUNS_DIR.glob("*/run_summary.json"):
        summary = _read_json(summary_path)
        if isinstance(summary, dict):
            summary["_run_dir"] = str(summary_path.parent)
            runs.append(summary)
    return sorted(runs, key=lambda item: item.get("created_at", ""), reverse=True)


def _load_memory_count() -> int:
    data = _read_json(MEMORY_FILE, {})
    memories = data.get("memories", []) if isinstance(data, dict) else []
    return len(memories) if isinstance(memories, list) else 0


def _load_global_rejection_count() -> int:
    if not GLOBAL_REJECTIONS_FILE.exists():
        return 0
    try:
        return sum(1 for line in GLOBAL_REJECTIONS_FILE.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _load_lesson_files() -> list[dict[str, str]]:
    lessons: list[dict[str, str]] = []
    if LESSONS_DIR.exists():
        for path in sorted(LESSONS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            lessons.append({"label": f"{path.stem.replace('-', ' ').title()} · latest", "path": str(path)})
    for run in _load_runs():
        run_dir = Path(run["_run_dir"])
        path = run_dir / "final_lesson.md"
        if path.exists():
            created = run.get("created_at", "")[:16].replace("T", " ")
            lessons.append({"label": f"{run.get('topic', path.stem)} · {created} · {run.get('status', 'unknown')}", "path": str(path)})
    # Keep each physical path once.
    unique: dict[str, dict[str, str]] = {}
    for item in lessons:
        unique[item["path"]] = item
    return list(unique.values())


def _status_badge(status: str) -> str:
    return {
        "passed": "🟢 PASSED",
        "passed_after_retry": "🟢 PASSED AFTER RETRY",
        "needs_review": "🟠 NEEDS REVIEW",
        "failed_max_retries": "🔴 FAILED — MAX RETRIES",
        "judge_unavailable": "🟠 JUDGE UNAVAILABLE",
    }.get(status, status.replace("_", " ").upper())


def _api_request(method: str, path: str, *, base_url: str, **kwargs: Any) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        response = requests.request(method, url, timeout=(5, 180), **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Cannot reach the tutor API at {base_url}. Start it in another terminal:\n"
            "uv run uvicorn app.api.application:app --reload --host 127.0.0.1 --port 8000\n\n"
            f"Technical detail: {exc}"
        ) from exc
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Tutor API returned HTTP {response.status_code}: {detail}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _render_overview() -> None:
    st.title("📚 LessonForge AI")
    st.caption("Self-evaluating lesson generation · persistent learning memory · conversational tutor")

    runs = _load_runs()
    latest = runs[0] if runs else None
    total_rejections = _load_global_rejection_count()
    memory_count = _load_memory_count()
    latest_status = latest.get("status", "No runs yet") if latest else "No runs yet"
    latest_sections = latest.get("sections", []) if latest else []
    passed_sections = sum(1 for item in latest_sections if item.get("status") in {"passed", "passed_after_retry"})
    section_total = len(latest_sections)
    pass_rate = (passed_sections / section_total * 100) if section_total else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lesson runs", len(runs))
    c2.metric("Latest run status", latest_status.replace("_", " ").title())
    c3.metric("Latest section pass rate", f"{pass_rate:.0f}%" if section_total else "—")
    c4.metric("Learned memory rules", memory_count)

    st.subheader("Assessment rubric · hard pass/fail")
    rubric = [
        ("accuracy", "Facts must be correct and grounded."),
        ("required_coverage", "The section must teach its required points."),
        ("beginner_friendly", "A learner starting from zero can follow it."),
        ("simple_language", "Use clear language suited to the target learner."),
        ("jargon_explanation", "Technical words must be explained."),
        ("example_quality", "Examples must be concrete and teach the idea."),
    ]
    rubric_cols = st.columns(3)
    for index, (name, description) in enumerate(rubric):
        with rubric_cols[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{name.replace('_', ' ').title()}**")
                st.caption(description)

    st.subheader("Assessment workflow")
    steps = [
        ("1 · Plan", "Create an ordered lesson plan for a beginner learner."),
        ("2 · Generate", "Generate each lesson section using the plan and relevant memory."),
        ("3 · Evaluate", "Apply six binary pass/fail criteria to each section."),
        ("4 · Regenerate", "Use evaluator feedback for up to two retries."),
        ("5 · Ship or flag", "Save the lesson, rejection log and run summary; flag sections that did not pass."),
        ("6 · Learn", "Persist repeated evaluator feedback for future runs."),
    ]
    cols = st.columns(3)
    for index, (heading, body) in enumerate(steps):
        with cols[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{heading}**")
                st.caption(body)

    with st.expander("Persistent memory inspection", expanded=False):
        memory_data = _read_json(MEMORY_FILE, {"memories": []})
        memory_items = memory_data.get("memories", []) if isinstance(memory_data, dict) else []
        if memory_items:
            st.dataframe(
                [
                    {
                        "Topic": item.get("topic", ""),
                        "Section": item.get("subtopic_title", ""),
                        "Criterion": item.get("criterion", ""),
                        "Learned rule": item.get("rule", ""),
                        "Occurrences": item.get("occurrences", 1),
                        "Last seen": item.get("last_seen", "")[:19],
                    }
                    for item in sorted(memory_items, key=lambda value: value.get("last_seen", ""), reverse=True)[:50]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No evaluator feedback has been saved to persistent memory yet.")

    st.subheader("Latest run")
    if latest:
        left, right = st.columns([1, 2])
        with left:
            st.markdown(f"### {_status_badge(latest_status)}")
            st.write(f"**Topic:** {latest.get('topic', '—')}")
            st.write(f"**Created:** {latest.get('created_at', '—')[:19].replace('T', ' ')}")
            st.write(f"**Rejections:** {latest.get('total_rejections', 0)}")
            st.write(f"**Run ID:** `{latest.get('run_id', '—')}`")
        with right:
            if latest_sections:
                st.dataframe(
                    [
                        {
                            "Section": item.get("title", item.get("id", "")),
                            "Status": _status_badge(item.get("status", "unknown")),
                            "Attempts": item.get("attempts", "—"),
                            "Failed criteria": ", ".join(item.get("failed_criteria", [])) or "—",
                        }
                        for item in latest_sections
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        lesson_path = Path(latest["_run_dir"]) / "final_lesson.md"
        if lesson_path.exists():
            st.download_button(
                "⬇ Download latest lesson",
                data=lesson_path.read_bytes(),
                file_name="lessonforge-latest-lesson.md",
                mime="text/markdown",
            )
    else:
        st.info("No runs found yet. Open **Generate lesson** to create your first lesson.")

    st.subheader("Submission checklist")
    st.markdown(
        "- [ ] Generate a standalone beginner lesson on **Introduction to RAG**.\n"
        "- [ ] Show pass/fail results for all six rubric criteria.\n"
        "- [ ] Demonstrate a deliberate error being caught by the evaluator.\n"
        "- [ ] Show regeneration (maximum two retries) and the rejection log.\n"
        "- [ ] Show persistent memory before and after a run.\n"
        "- [ ] Record a 15–20 minute face-visible walkthrough."
    )


def _render_generate() -> None:
    st.title("🧪 Generate a lesson")
    st.caption("This calls your existing LessonWorkflow directly. It does not replace or modify the generation pipeline.")

    with st.form("generate_lesson_form"):
        topic = st.text_input("Lesson topic", value="Introduction to RAG")
        learner_profile = st.text_area(
            "Target learner",
            value=(
                "Indian 12th-grade graduate, limited English vocabulary, "
                "non-English-medium background, no technical background, "
                "wants to start an AI career."
            ),
            height=90,
        )
        c1, c2, c3 = st.columns(3)
        lesson_minutes = c1.slider("Lesson length (minutes)", 10, 60, 20, 5)
        min_subtopics = c2.number_input("Minimum sections", min_value=3, max_value=12, value=5)
        max_subtopics = c3.number_input("Maximum sections", min_value=int(min_subtopics), max_value=15, value=max(7, int(min_subtopics)))
        source_facts_text = st.text_area(
            "Grounding facts (one per line)",
            value=(
                "RAG stands for Retrieval-Augmented Generation.\n"
                "RAG retrieves relevant information before an AI model generates an answer.\n"
                "RAG can reduce hallucinations but cannot eliminate them completely."
            ),
            height=110,
        )
        extra_rules_text = st.text_area(
            "Additional instructions (one per line)",
            value="Explain technical terms in simple English.\nUse everyday examples relevant to an Indian learner.",
            height=90,
        )
        st.info("The assessment allows an initial attempt plus at most two retries for a failed section.")
        submitted = st.form_submit_button("🚀 Generate and evaluate lesson", type="primary", use_container_width=True)

    if submitted:
        if not topic.strip() or len(learner_profile.strip()) < 5:
            st.error("Enter a topic and a meaningful target learner description.")
            return
        if int(max_subtopics) < int(min_subtopics):
            st.error("Maximum sections must be greater than or equal to minimum sections.")
            return

        source_facts = [line.strip() for line in source_facts_text.splitlines() if line.strip()]
        extra_rules = [line.strip() for line in extra_rules_text.splitlines() if line.strip()]
        log_buffer = io.StringIO()
        try:
            from app.workflow.lesson_workflow import LessonWorkflow

            workflow = LessonWorkflow(output_dir=str(OUTPUTS_DIR))
            with st.spinner("Planning, generating, evaluating and revising the lesson. This can take several minutes..."):
                with contextlib.redirect_stdout(log_buffer):
                    lesson = workflow.run(
                        topic=topic.strip(),
                        learner_profile=learner_profile.strip(),
                        lesson_minutes=int(lesson_minutes),
                        min_subtopics=int(min_subtopics),
                        max_subtopics=int(max_subtopics),
                        source_facts=source_facts,
                        extra_rules=extra_rules,
                    )
            st.session_state["last_generated_run_id"] = (workflow.last_run or {}).get("run_id")
            st.session_state["last_generated_lesson"] = lesson
            st.session_state["last_generation_log"] = log_buffer.getvalue()
            st.success("Lesson workflow completed. Open Run inspector to review the evaluator and rejection log.")
            if workflow.last_run:
                st.write(f"**Overall status:** {_status_badge(workflow.last_run.get('status', 'unknown'))}")
                st.write(f"**Run ID:** `{workflow.last_run.get('run_id')}`")
        except Exception as exc:
            st.error(f"Lesson generation failed: {exc}")
            st.session_state["last_generation_log"] = log_buffer.getvalue()

    if st.session_state.get("last_generation_log"):
        with st.expander("View workflow execution log", expanded=False):
            st.code(st.session_state["last_generation_log"], language="text")
    if st.session_state.get("last_generated_lesson"):
        st.subheader("Generated lesson preview")
        st.markdown(st.session_state["last_generated_lesson"])
        st.download_button(
            "⬇ Download generated lesson",
            data=st.session_state["last_generated_lesson"],
            file_name="lessonforge-generated-lesson.md",
            mime="text/markdown",
        )


def _render_run_inspector() -> None:
    st.title("🔍 Run inspector")
    runs = _load_runs()
    if not runs:
        st.info("No run summaries found. Generate a lesson first.")
        return

    labels = {
        f"{run.get('topic', 'Untitled')} · {run.get('created_at', '')[:16].replace('T', ' ')} · {run.get('status', '')}": run
        for run in runs
    }
    selected_label = st.selectbox("Select a run", list(labels.keys()))
    run = labels[selected_label]
    run_dir = Path(run["_run_dir"])
    sections = run.get("sections", [])
    passed = sum(1 for item in sections if item.get("status") in {"passed", "passed_after_retry"})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall status", run.get("status", "—").replace("_", " ").title())
    c2.metric("Sections passed", f"{passed}/{len(sections)}")
    c3.metric("Total rejections", run.get("total_rejections", 0))
    c4.metric("Max retries", run.get("max_retries_per_subtopic", 2))

    st.subheader("Section-by-section evaluation")
    st.dataframe(
        [
            {
                "ID": item.get("id"),
                "Section": item.get("title"),
                "Status": _status_badge(item.get("status", "unknown")),
                "Attempts": item.get("attempts", "—"),
                "Failed criteria": ", ".join(item.get("failed_criteria", [])) or "—",
            }
            for item in sections
        ],
        use_container_width=True,
        hide_index=True,
    )

    rejection_path = run_dir / "rejection_log.json"
    rejection_log = _read_json(rejection_path, [])
    st.subheader("Rejection log")
    if not rejection_log:
        st.success("No rejected attempts were recorded for this run.")
    else:
        st.caption(f"{len(rejection_log)} rejected attempt(s). Each record shows what failed and the retry outcome.")
        for item in rejection_log:
            title = item.get("subtopic_title", item.get("subtopic_id", "Section"))
            attempt = item.get("attempt", "?")
            failed = ", ".join(item.get("failed_criteria", [])) or "criteria unavailable"
            with st.expander(f"{title} · Attempt {attempt} · {failed}"):
                st.write("**Why it failed**")
                for reason in item.get("reasons", []):
                    st.markdown(f"- {reason}")
                st.write(f"**Retry result:** {item.get('retry_result', 'Not recorded')}")
                if item.get("rejected_content"):
                    with st.expander("Rejected content"):
                        st.markdown(item["rejected_content"])

    summary_path = run_dir / "run_summary.json"
    lesson_path = run_dir / "final_lesson.md"
    col_a, col_b = st.columns(2)
    if summary_path.exists():
        col_a.download_button("⬇ Download run summary JSON", summary_path.read_bytes(), file_name=f"{run.get('run_id', 'run')}-summary.json", mime="application/json")
    if rejection_path.exists():
        col_b.download_button("⬇ Download rejection log JSON", rejection_path.read_bytes(), file_name=f"{run.get('run_id', 'run')}-rejections.json", mime="application/json")
    if lesson_path.exists():
        st.download_button("⬇ Download final lesson", lesson_path.read_bytes(), file_name=f"{run.get('run_id', 'lesson')}.md", mime="text/markdown")


def _render_library() -> None:
    st.title("📖 Lesson library")
    lessons = _load_lesson_files()
    if not lessons:
        st.info("No lesson files found. Generate a lesson first.")
        return
    labels = [item["label"] for item in lessons]
    chosen = st.selectbox("Choose a lesson", labels)
    selected = next(item for item in lessons if item["label"] == chosen)
    path = Path(selected["path"])
    content = path.read_text(encoding="utf-8")
    st.caption(str(path.relative_to(PROJECT_ROOT)))
    st.markdown(content)
    st.download_button("⬇ Download Markdown", data=content, file_name=path.name, mime="text/markdown")


def _render_evaluator_demo() -> None:
    st.title("🧯 Evaluator demonstration")
    st.caption("A controlled, isolated demonstration using the same LessonEvaluator as the production workflow.")
    st.warning("This demo evaluates a deliberately flawed sample. It does not write to the normal rejection log or update lesson memory.")

    flawed_default = (
        "RAG stands for Retrieval-Augmented Generation. It retrieves relevant information "
        "before an AI model generates an answer. RAG guarantees that the AI will never "
        "give a wrong or made-up answer."
    )
    flawed_content = st.text_area("Deliberately flawed lesson section", value=flawed_default, height=150)
    source_facts = [
        "RAG retrieves relevant information before an AI model generates an answer.",
        "RAG can reduce hallucinations but cannot eliminate them completely.",
        "The retrieved information may be incomplete, outdated, or incorrect.",
    ]
    st.caption("Expected issue: the sample falsely claims that RAG guarantees perfectly correct answers.")

    if st.button("Run the real evaluator on this sample", type="primary"):
        try:
            from app.agents.evaluator import LessonEvaluator
            from app.agents.schemas import LessonSubtopic

            subtopic = LessonSubtopic(
                id="DEMO-1",
                title="What RAG can and cannot guarantee",
                type="core",
                must_teach=[
                    "Explain what RAG does.",
                    "Explain that RAG can reduce but cannot eliminate hallucinations.",
                ],
                key_terms=["RAG", "hallucination"],
                example_idea="A library assistant searching trusted notes before answering.",
                builds_on=[],
            )
            evaluator = LessonEvaluator()
            with st.spinner("The evaluator is checking the sample against all six criteria..."):
                result = evaluator.evaluate(
                    topic="Introduction to RAG",
                    learner_profile="Indian 12th-grade learner with limited English and no technical background.",
                    subtopic=subtopic,
                    generated_content=flawed_content,
                    source_facts=source_facts,
                    previous_content="",
                )
            if result.passed:
                st.error("The evaluator passed this sample. The deliberate error was not caught in this run. Do not present this as a successful demo.")
            else:
                st.success(f"Evaluator rejected the sample. Failed criteria: {', '.join(result.failed_criteria)}")
            st.dataframe(
                [
                    {
                        "Criterion": item.criterion,
                        "Result": item.result,
                        "Evidence": item.evidence,
                        "Feedback": item.feedback or "—",
                    }
                    for item in result.criteria
                ],
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.error(f"Evaluator demo failed: {exc}")


def _render_tutor(base_url: str) -> None:
    st.title("💬 Conversational AI tutor")
    st.caption("Ask questions about a generated lesson, request simple explanations, see examples and practise with quizzes.")

    api_ok = False
    try:
        health = _api_request("GET", "/health", base_url=base_url)
        api_ok = health.get("status") == "ok"
    except RuntimeError as exc:
        st.error(str(exc))
    if not api_ok:
        st.info("Start the separate tutor API in another PowerShell window. The lesson generator remains a separate workflow.")
        return

    lesson_items = _load_lesson_files()
    chat_items = _api_request("GET", "/api/tutor/chats", base_url=base_url)

    with st.expander("Start a new conversation", expanded=not bool(st.session_state.get("active_tutor_chat_id"))):
        if not lesson_items:
            st.info("Generate or save a lesson before starting a tutor conversation.")
        else:
            lesson_labels = [item["label"] for item in lesson_items]
            selected_lesson_label = st.selectbox("Select lesson", lesson_labels, key="new_tutor_lesson")
            if st.button("Create tutor chat", type="primary"):
                lesson_item = next(item for item in lesson_items if item["label"] == selected_lesson_label)
                lesson_text = Path(lesson_item["path"]).read_text(encoding="utf-8")
                if len(lesson_text) > 30000:
                    st.error("This lesson is longer than the tutor API's 30,000-character limit. Choose a shorter lesson or reduce the lesson length.")
                else:
                    created = _api_request(
                        "POST",
                        "/api/tutor/chats",
                        base_url=base_url,
                        json={"lesson_title": selected_lesson_label.split(" · ")[0], "lesson_content": lesson_text},
                    )
                    st.session_state["active_tutor_chat_id"] = created["chat_id"]
                    st.session_state.pop("active_tutor_quiz", None)
                    st.success("Tutor conversation created.")
                    st.rerun()

    if chat_items:
        chat_labels = {
            f"{item['lesson_title']} · {item['updated_at'][:16].replace('T', ' ')} · {item['chat_id'][:8]}": item["chat_id"]
            for item in chat_items
        }
        current_id = st.session_state.get("active_tutor_chat_id")
        default_index = 0
        if current_id in chat_labels.values():
            default_index = list(chat_labels.values()).index(current_id)
        chosen_chat_label = st.selectbox("Saved conversations", list(chat_labels.keys()), index=default_index)
        chosen_chat_id = chat_labels[chosen_chat_label]
        if chosen_chat_id != current_id:
            st.session_state["active_tutor_chat_id"] = chosen_chat_id
            st.session_state.pop("active_tutor_quiz", None)
            st.rerun()

    chat_id = st.session_state.get("active_tutor_chat_id")
    if not chat_id:
        st.info("Create a new tutor conversation or select a saved one.")
        return

    history = _api_request("GET", f"/api/tutor/chats/{chat_id}/messages", base_url=base_url)
    st.markdown(f"**Lesson:** {history.get('lesson_title', 'Lesson')}")
    for item in history.get("messages", []):
        role = item.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(item.get("content", ""))
            if item.get("mode") in {"explain", "example", "quiz"}:
                st.caption(item["mode"].title())

    mode_col, quiz_col = st.columns([2, 1])
    with mode_col:
        mode = st.selectbox("Response style", ["chat", "explain", "example"], format_func=lambda value: {
            "chat": "Ask anything about this lesson",
            "explain": "Explain simply, step by step",
            "example": "Give practical examples",
        }[value])
    with quiz_col:
        if st.button("🎯 Generate quiz", use_container_width=True):
            try:
                quiz = _api_request("POST", f"/api/tutor/chats/{chat_id}/quiz", base_url=base_url)
                st.session_state["active_tutor_quiz"] = quiz
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))

    quiz = st.session_state.get("active_tutor_quiz")
    if quiz and quiz.get("chat_id") == chat_id:
        with st.container(border=True):
            st.markdown("#### Quick knowledge check")
            st.write(quiz["question"])
            options = quiz.get("options", [])
            option_labels = {f"{item['id']}. {item['text']}": item["id"] for item in options}
            selected_option_label = st.radio("Choose one answer", list(option_labels.keys()), key=f"quiz_choice_{chat_id}")
            if st.button("Submit quiz answer", type="primary"):
                try:
                    result = _api_request(
                        "POST",
                        f"/api/tutor/chats/{chat_id}/quiz/answer",
                        base_url=base_url,
                        json={"option_id": option_labels[selected_option_label]},
                    )
                    st.session_state["last_quiz_result"] = result
                    st.session_state.pop("active_tutor_quiz", None)
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
    last_result = st.session_state.get("last_quiz_result")
    if last_result and last_result.get("chat_id") == chat_id:
        if last_result.get("correct"):
            st.success("Correct! " + last_result.get("feedback", ""))
        else:
            st.warning("Not quite. " + last_result.get("feedback", ""))

    prompt = st.chat_input("Ask a question about this lesson...")
    if prompt:
        try:
            _api_request(
                "POST",
                f"/api/tutor/chats/{chat_id}/messages",
                base_url=base_url,
                json={"message": prompt, "mode": mode},
            )
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))


def main() -> None:
    st.sidebar.title("📚 LessonForge AI")
    st.sidebar.caption("Content systems workbench")
    page = st.sidebar.radio(
        "Workspace",
        ["Overview", "Generate lesson", "Run inspector", "Lesson library", "Evaluator demo", "AI tutor"],
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    api_base_url = st.sidebar.text_input("Tutor API URL", value="http://127.0.0.1:8000")
    st.sidebar.caption("The tutor API is a separate process. Lesson generation runs directly in this Streamlit app.")
    st.sidebar.divider()
    st.sidebar.caption("Assessment focus")
    st.sidebar.markdown("- Generate → Evaluate → Regenerate\n- Six pass/fail checks\n- Maximum two retries\n- Rejection log + persistent memory")

    if page == "Overview":
        _render_overview()
    elif page == "Generate lesson":
        _render_generate()
    elif page == "Run inspector":
        _render_run_inspector()
    elif page == "Lesson library":
        _render_library()
    elif page == "Evaluator demo":
        _render_evaluator_demo()
    elif page == "AI tutor":
        _render_tutor(api_base_url)


if __name__ == "__main__":
    main()
