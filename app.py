import os
import re
from pathlib import Path
from typing import Dict, List, Any

from flask import Flask, jsonify, render_template, request, abort
from pypdf import PdfReader

BASE_DIR = Path(__file__).parent.resolve()
TESTS_DIR = BASE_DIR / "tests"

app = Flask(__name__, static_folder="static", template_folder="templates")


def _lines_from_pdf(path: Path) -> List[str]:
    reader = PdfReader(str(path))
    lines: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                lines.append(line)
    return lines


def _parse_question_blocks(text: str) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    block_pattern = re.compile(
        r"(?m)(\d{1,3})\s*[).:\-]\s*(.+?)(?=\n\d{1,3}\s*[).:\-]|\Z)", re.S
    )
    opt_block_pattern = re.compile(r"(?i)([A-E])[\).:\-]\s*(.+?)(?=([A-E])[\).:\-]|\Z)", re.S)
    for match in block_pattern.finditer(text):
        number = int(match.group(1))
        body = match.group(2).strip()
        if not body:
            continue
        opts = []
        opt_match = list(opt_block_pattern.finditer(body))
        if opt_match:
            question_text = body[: opt_match[0].start()].strip()
            for om in opt_match:
                label = om.group(1).upper()
                opt_text = om.group(2).strip().replace("\n", " ")
                if opt_text:
                    opts.append({"label": label, "text": opt_text})
        else:
            question_text = body
        questions.append(
            {
                "number": number,
                "prompt": question_text.replace("\n", " ").strip(),
                "options": opts,
            }
        )
    return questions


def _split_inline_options(text: str) -> tuple[str, List[Dict[str, str]]]:
    """Split options embedded on the same line as the question or another option."""
    opt_pattern = re.compile(r"([A-E])[\).:\-]\s*")
    matches = list(opt_pattern.finditer(text))
    if not matches:
        return text.strip(), []
    parts: List[Dict[str, str]] = []
    prefix = text[: matches[0].start()].strip()
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            parts.append({"label": match.group(1).upper(), "text": body})
    return prefix, parts


def _find_answer_section_start(lines: List[str]) -> int:
    for idx in range(len(lines) - 1, -1, -1):
        if re.search(r"answer\s*(key|section)?", lines[idx], re.IGNORECASE):
            return idx
    # Fallback: assume answers live near the end
    return max(len(lines) - max(10, len(lines) // 3), 0)


def _parse_answer_key(lines: List[str], start: int) -> Dict[int, Dict[str, str]]:
    # Anchor at line start to avoid accidental matches inside explanations.
    answer_pattern = re.compile(r"^\s*(\d{1,3})\s*[:.\-)]?\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    answers: Dict[int, Dict[str, str]] = {}
    i = start
    while i < len(lines):
        line = lines[i]
        match = answer_pattern.match(line)
        if not match:
            i += 1
            continue
        number = int(match.group(1))
        letter = match.group(2).upper()
        explanation_parts: List[str] = []
        remainder = match.group(3).strip()
        if remainder:
            explanation_parts.append(remainder)
        i += 1
        # Capture subsequent lines until next answer entry.
        while i < len(lines):
            lookahead = lines[i]
            if answer_pattern.match(lookahead):
                break
            if lookahead.strip():
                explanation_parts.append(lookahead.strip())
            i += 1
        answers[number] = {
            "letter": letter,
            "explanation": " ".join(explanation_parts).strip(),
        }
    # If we clearly missed most answers, scan the whole document as a fallback
    if len(answers) < 50:
        i = 0
        while i < len(lines):
            line = lines[i]
            match = answer_pattern.match(line)
            if not match:
                i += 1
                continue
            number = int(match.group(1))
            letter = match.group(2).upper()
            if number in answers:
                i += 1
                continue
            explanation_parts: List[str] = []
            remainder = match.group(3).strip()
            if remainder:
                explanation_parts.append(remainder)
            i += 1
            while i < len(lines):
                lookahead = lines[i]
                if answer_pattern.match(lookahead):
                    break
                if lookahead.strip():
                    explanation_parts.append(lookahead.strip())
                i += 1
            answers[number] = {
                "letter": letter,
                "explanation": " ".join(explanation_parts).strip(),
            }
    return answers


def _parse_questions(lines: List[str], stop: int | None = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    q_pattern = re.compile(r"^(\d{1,3})\s*[).:\-]?\s+(.*)")
    opt_pattern = re.compile(r"^\s*([A-E])[\).:\-]?\s*(.*)")
    current: Dict[str, Any] = {}
    iterable = lines if stop is None else lines[:stop]
    chunk_pattern = re.compile(r"(?:^|\s)(\d{1,3})\s*[).:\-]\s+")

    def split_line(line: str) -> List[str]:
        parts: List[str] = []
        matches = list(chunk_pattern.finditer(line))
        if not matches:
            return [line]
        for idx, match in enumerate(matches):
            start = match.start(1)
            end = matches[idx + 1].start(1) if idx + 1 < len(matches) else len(line)
            parts.append(line[start:end].strip())
        return [p for p in parts if p]

    for raw_line in iterable:
        for line in split_line(raw_line):
            q_match = q_pattern.match(line)
            if q_match:
                if current:
                    questions.append(current)
                current = {
                    "number": int(q_match.group(1)),
                    "prompt": "",
                    "options": [],
                }
                q_text, inline_opts = _split_inline_options(q_match.group(2))
                current["prompt"] = q_text
                if inline_opts:
                    current["options"].extend(inline_opts)
                continue

            if not current:
                continue

            opt_match = opt_pattern.match(line)
            if opt_match:
                current["options"].append(
                    {"label": opt_match.group(1).upper(), "text": opt_match.group(2).strip()}
                )
                continue

            prefix_text, inline_opts = _split_inline_options(line)
            if inline_opts:
                if prefix_text:
                    if current["options"]:
                        current["options"][-1]["text"] += f" {prefix_text}"
                    else:
                        current["prompt"] += f" {prefix_text}"
                current["options"].extend(inline_opts)
            else:
                # Attach extra text to the last seen chunk
                if current["options"]:
                    current["options"][-1]["text"] += f" {line.strip()}"
                else:
                    current["prompt"] += f" {line.strip()}"

    if current:
        questions.append(current)
    return questions


def _attach_answers(test_id: str, questions: List[Dict[str, Any]], answers: Dict[int, Dict[str, str]]) -> List[Dict[str, Any]]:
    paired: List[Dict[str, Any]] = []
    seen_numbers = set()
    for q in questions:
        if q["number"] in seen_numbers:
            continue
        ans_blob = answers.get(q["number"])
        if not ans_blob:
            continue
        ans_letter = ans_blob["letter"]
        if not q["options"]:
            # Without options we cannot run multiple choice practice
            continue
        correct_index = None
        for idx, opt in enumerate(q["options"]):
            if opt["label"].upper() == ans_letter:
                correct_index = idx
                break
        if correct_index is None:
            fallback_idx = ord(ans_letter) - ord("A")
            if 0 <= fallback_idx < len(q["options"]):
                correct_index = fallback_idx
        if correct_index is None:
            continue
        seen_numbers.add(q["number"])
        paired.append(
            {
                "id": f"{test_id}-q{q['number']}",
                "number": q["number"],
                "question": q["prompt"].strip(),
                "options": [opt["text"].strip() for opt in q["options"]],
                "correct_index": correct_index,
                "correct_letter": ans_letter,
                "explanation": ans_blob.get("explanation", "").strip(),
            }
        )
    return paired


def _parse_pdf_to_test(path: Path) -> Dict[str, Any]:
    lines = _lines_from_pdf(path)
    if not lines:
        return {}
    answer_start = _find_answer_section_start(lines)
    answers = _parse_answer_key(lines, answer_start)
    text = "\n".join(lines)
    sources: List[List[Dict[str, Any]]] = []
    block_parsed = _parse_question_blocks(text)
    if block_parsed:
        sources.append(block_parsed)
    stop_parsed = _parse_questions(lines, stop=answer_start)
    if stop_parsed:
        sources.insert(0, stop_parsed)  # prefer clean split before answer key
    full_parsed = _parse_questions(lines)
    if full_parsed:
        sources.append(full_parsed)

    merged: Dict[int, Dict[str, Any]] = {}
    for source in sources:
        for q in source:
            if q["number"] not in merged and q.get("options"):
                merged[q["number"]] = q

    questions_raw = list(merged.values())
    test_id = path.stem
    questions = _attach_answers(test_id, questions_raw, answers)
    questions = sorted(questions, key=lambda q: q["number"])
    return {
        "id": test_id,
        "name": path.stem.replace("_", " ").title(),
        "description": f"Parsed from {path.name}",
        "questions": questions,
    }


_CACHE: Dict[str, Any] = {"stamp": 0.0, "tests": {}, "files": []}


def load_all_tests() -> Dict[str, Dict[str, Any]]:
    """Read every PDF test file from the tests directory with lightweight caching."""
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(TESTS_DIR.glob("*.pdf"))
    names = [p.name for p in pdf_paths]
    stamp = max((p.stat().st_mtime for p in pdf_paths), default=0.0)
    if _CACHE["tests"] and stamp <= _CACHE["stamp"] and names == _CACHE.get("files"):
        return _CACHE["tests"]

    tests: Dict[str, Dict[str, Any]] = {}
    for path in pdf_paths:
        try:
            parsed = _parse_pdf_to_test(path)
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"Skipping {path.name}: {exc}")
            continue
        if not parsed or not parsed.get("questions"):
            print(f"Skipping {path.name}: no questions/answers parsed.")
            continue
        # Ensure questions are sorted by their numeric order and limited to 1-100
        parsed["questions"] = sorted(parsed["questions"], key=lambda q: q.get("number", 0))
        tests[parsed["id"]] = parsed

    _CACHE["tests"] = tests
    _CACHE["stamp"] = stamp
    _CACHE["files"] = names
    return tests


def _get_test_or_404(test_id: str) -> Dict[str, Any]:
    tests = load_all_tests()
    test = tests.get(test_id)
    if not test:
        abort(404, description="Test not found")
    return test


def _get_question_or_404(test: Dict[str, Any], question_id: str) -> Dict[str, Any]:
    for question in test["questions"]:
        if question["id"] == question_id:
            return question
    abort(404, description="Question not found")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/tests")
def list_tests():
    tests = load_all_tests()
    payload = [
        {
            "id": test["id"],
            "name": test["name"],
            "description": test.get("description", ""),
            "question_count": len(test["questions"]),
        }
        for test in tests.values()
    ]
    return jsonify(payload)


@app.route("/api/tests/<test_id>/questions")
def get_questions(test_id: str):
    test = _get_test_or_404(test_id)
    questions = list(test["questions"])
    count_param = request.args.get("count")
    if count_param:
        try:
            desired = int(count_param)
            if desired > 0:
                desired = min(desired, len(questions))
                questions = questions[:desired]
        except ValueError:
            pass
    sanitized = [
        {
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
            "number": q.get("number"),
        }
        for q in questions
    ]
    return jsonify(
        {
            "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
            "questions": sanitized,
            "selected_count": len(sanitized),
        }
    )


@app.route("/api/tests/<test_id>/check/<question_id>", methods=["POST"])
def check_answer(test_id: str, question_id: str):
    test = _get_test_or_404(test_id)
    question = _get_question_or_404(test, question_id)
    payload = request.get_json(silent=True) or {}
    if "choice" not in payload:
        abort(400, description="Missing 'choice' in request body.")
    try:
        choice_index = int(payload["choice"])
    except Exception:
        abort(400, description="'choice' must be an integer.")
    if choice_index < 0 or choice_index >= len(question["options"]):
        abort(400, description="Choice index is out of range.")
    is_correct = choice_index == question["correct_index"]
    return jsonify({"correct": is_correct})


@app.route("/api/tests/<test_id>/answer/<question_id>")
def reveal_answer(test_id: str, question_id: str):
    test = _get_test_or_404(test_id)
    question = _get_question_or_404(test, question_id)
    return jsonify(
        {
            "correct_index": question["correct_index"],
            "correct_letter": question.get("correct_letter", ""),
            "explanation": question.get("explanation", ""),
        }
    )


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5001"))
    app.run(host=host, port=port, debug=False)
