import io
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional, IO

from flask import Flask, jsonify, render_template, request, abort, redirect, url_for, session
from pypdf import PdfReader
from werkzeug.exceptions import HTTPException

BASE_DIR = Path(__file__).parent.resolve()
TESTS_DIR = BASE_DIR / "tests"
MAX_QUESTIONS_PER_RUN = int(os.getenv("MAX_QUESTIONS_PER_RUN", "100"))
MAX_TIME_LIMIT_MINUTES = int(os.getenv("MAX_TIME_LIMIT_MINUTES", "180"))
DEFAULT_RANDOM_ORDER = os.getenv("DEFAULT_RANDOM_ORDER", "false").lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "12582912"))  # 12 MB default
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_TYPE="filesystem",
)


@app.errorhandler(HTTPException)
def _json_http_error(exc: HTTPException):
    """Return consistent JSON errors for API routes."""
    if request.path.startswith("/api/"):
        response = exc.get_response()
        payload = {"error": exc.name, "description": exc.description}
        response.data = json.dumps(payload)
        response.content_type = "application/json"
        response.status_code = exc.code or 500
        return response
    return exc


@app.errorhandler(Exception)
def _json_generic_error(exc: Exception):
    """Fallback JSON error surface for unexpected API failures."""
    if isinstance(exc, HTTPException):
        return _json_http_error(exc)
    if request.path.startswith("/api/"):
        app.logger.exception("Unhandled error during API request")
        return jsonify({"error": "Internal Server Error", "description": str(exc)}), 500
    raise exc


def _lines_from_pdf(source: Path | IO[bytes], footer_hint: Optional[str] = None) -> List[str]:
    """Extract lines from a PDF while preserving order and trimming repeated footer noise."""
    def _looks_like_header_line(text: str) -> bool:
        patterns = [
            r"(?i)\bcluster\b",
            r"(?i)\bcareer\s+cluster\b",
            r"(?i)\btest\s*(number|#)\b",
            r"(?i)\bdeca\b",
            r"(?i)\bexam\b",
            r"(?i)^page\s+\d+",
            r"^\d+\s*(of|/)\s*\d+$",
        ]
        if any(re.search(p, text) for p in patterns):
            return True
        tokens = text.split()
        if len(tokens) >= 4 and all(tok.isupper() or re.fullmatch(r"[A-Z0-9\-]+", tok) for tok in tokens):
            return True
        return False
    reader = PdfReader(source)
    lines: List[str] = []
    footer_tokens: List[str] = []
    if footer_hint:
        normalized = re.sub(r"[_\-]+", " ", footer_hint)
        normalized = re.sub(r"\s{2,}", " ", normalized).strip()
        if normalized:
            footer_tokens.append(normalized)
            upper_variant = normalized.upper()
            if upper_variant != normalized:
                footer_tokens.append(upper_variant)

    def strip_footer(text: str) -> str:
        if not footer_tokens:
            return text
        cleaned = text
        for token in footer_tokens:
            cleaned = re.sub(
                rf"\s*(?:[–—-]|•)?\s*{re.escape(token)}\s*$",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
        return cleaned.strip()

    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                # Remove duplicated internal spacing that can scramble tokens
                line = re.sub(r"\s{2,}", " ", line)
                line = strip_footer(line)
                if line:
                    if not _looks_like_header_line(line):
                        lines.append(line)
    # Drop page headers that repeat across pages (often cluster title / test number).
    freq: Dict[str, int] = {}
    for line in lines:
        freq[line] = freq.get(line, 0) + 1
    header_like = {
        line
        for line, count in freq.items()
        if count >= 2
        and not re.match(r"^\d{1,3}\s*[).:\-]", line)  # question start
        and not re.match(r"^[A-E][).:\-]", line)  # option start
        and _looks_like_header_line(line)
    }
    if header_like:
        lines = [ln for ln in lines if ln not in header_like]
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


def _explode_answer_lines(lines: List[str]) -> List[str]:
    """Split dense answer key lines like '97.B 98.C' into separate lines."""
    answer_chunk = re.compile(r"(?<!\d)(\d{1,3})\s*[:.\-)]?\s*[A-E]\b", re.IGNORECASE)
    expanded: List[str] = []
    for line in lines:
        matches = list(answer_chunk.finditer(line))
        if len(matches) <= 1:
            expanded.append(line)
            continue
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            chunk = line[start:end].strip()
            if chunk:
                expanded.append(chunk)
    return expanded


def _parse_answer_key(lines: List[str], start: int, raw_text: str) -> Dict[int, Dict[str, str]]:
    """Parse answers plus explanations with guards for scrambled tail sections."""
    # Allow a bit of prefix noise (e.g., copyright text before "1.A") but avoid matching mid-number years.
    answer_pattern = re.compile(
        r"(?<!\d)(\d{1,3})\s*[:.\-)]?\s*([A-E])\b\s*(.*)", re.IGNORECASE
    )
    answers: Dict[int, Dict[str, str]] = {}
    expanded_lines = _explode_answer_lines(lines[start:])

    def harvest(line_iterable: List[str]):
        i = 0
        while i < len(line_iterable):
            line = line_iterable[i]
            match = answer_pattern.search(line)
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
            while i < len(line_iterable):
                lookahead = line_iterable[i]
                if answer_pattern.search(lookahead):
                    break
                if lookahead.strip():
                    explanation_parts.append(lookahead.strip())
                i += 1
            if 1 <= number <= 100:  # keep strict bounds
                answers[number] = {
                    "letter": letter,
                    "explanation": " ".join(explanation_parts).strip(),
                }

    # Primary pass (dedicated answer slice)
    harvest(expanded_lines)

    # If we clearly missed many answers, scan the whole document as a fallback
    if len(answers) < 80:
        harvest(_explode_answer_lines(lines))

    # Last-resort scan directly on text to catch tightly packed keys near EOF
    if len(answers) < 80:
        blob_pattern = re.compile(
            r"(?<!\d)(\d{1,3})\s*[:.\-)]?\s*([A-E])\b(?:\s*(.*?))(?=(?<!\d)\d{1,3}\s*[:.\-)]?\s*[A-E]\b|\Z)",
            re.IGNORECASE | re.S,
        )
        for match in blob_pattern.finditer(raw_text):
            number = int(match.group(1))
            letter = match.group(2).upper()
            explanation = (match.group(3) or "").replace("\n", " ").strip()
            if 1 <= number <= 100 and number not in answers:
                answers[number] = {"letter": letter, "explanation": explanation}

    # Normalize ordering and enforce 1..100 bounds
    cleaned = {
        n: answers[n]
        for n in sorted(num for num in answers.keys() if 1 <= num <= 100)
    }
    return cleaned


def _parse_questions(lines: List[str], stop: int | None = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    q_pattern = re.compile(r"^(\d{1,3})\s*[).:\-]?\s+(.*)")
    opt_pattern = re.compile(r"^\s*([A-E])[\).:\-]?\s*(.*)")
    current: Dict[str, Any] = {}
    iterable = lines if stop is None else lines[:stop]
    chunk_pattern = re.compile(r"(?:^|\s)(\d{1,3})\s*[).:\-]\s+")
    header_guard = re.compile(
        r"(?i)(cluster|career cluster|test\s*(number|#)|deca|exam|page\s+\d+|\d+\s*(of|/)\s*\d+)"
    )

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
                if header_guard.search(opt_match.group(2) or ""):
                    continue
                
                # Splitting embedded options even if the line starts with one (e.g. "A. Text C. Text")
                label = opt_match.group(1).upper()
                remainder = opt_match.group(2)
                
                more_prefix, more_opts = _split_inline_options(remainder)
                
                current["options"].append(
                    {"label": label, "text": more_prefix}
                )
                if more_opts:
                     current["options"].extend(
                        [opt for opt in more_opts if not header_guard.search(opt.get("text", ""))]
                     )
                continue

            prefix_text, inline_opts = _split_inline_options(line)
            if inline_opts:
                if prefix_text:
                    if current["options"] and not header_guard.search(prefix_text):
                        current["options"][-1]["text"] += f" {prefix_text}"
                    else:
                        if not header_guard.search(prefix_text):
                            current["prompt"] += f" {prefix_text}"
                current["options"].extend(
                    [opt for opt in inline_opts if not header_guard.search(opt.get("text", ""))]
                )
            else:
                # Attach extra text to the last seen chunk
                if current["options"] and not header_guard.search(line):
                    current["options"][-1]["text"] += f" {line.strip()}"
                elif not header_guard.search(line):
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
        fallback_idx = ord(ans_letter) - ord("A")
        if correct_index is None and 0 <= fallback_idx < len(q["options"]):
            correct_index = fallback_idx
        # As a last resort, keep the question with a safe index to avoid dropping it entirely
        if correct_index is None and q["options"]:
            correct_index = min(len(q["options"]) - 1, max(0, fallback_idx if fallback_idx >= 0 else 0))
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


def _slugify(value: str, fallback: str = "test") -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", value).strip("-").lower()
    return slug or fallback


def _parse_uploaded_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    name_hint = Path(filename).stem if filename else "uploaded-test"
    stream = io.BytesIO(file_bytes)
    return _parse_pdf_source(stream, name_hint=name_hint, description_hint=f"Uploaded: {filename or 'PDF'}")


def _parse_pdf_to_test(path: Path) -> Dict[str, Any]:
    return _parse_pdf_source(path, name_hint=path.stem, description_hint=f"Parsed from {path.name}")


def _parse_pdf_source(source: Path | IO[bytes], name_hint: str, description_hint: Optional[str] = None) -> Dict[str, Any]:
    """Parse a PDF from a path or file-like into a test structure."""
    normalized_name_hint = re.sub(r"\s{2,}", " ", re.sub(r"[_\-]+", " ", name_hint)).strip() or "Uploaded Test"
    lines = _lines_from_pdf(source, footer_hint=normalized_name_hint)
    if not lines:
        return {}
    text = "\n".join(lines)
    answer_start = _find_answer_section_start(lines)
    answers = _parse_answer_key(lines, answer_start, text)
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
    for source_block in sources:
        for q in source_block:
            if q["number"] not in merged and q.get("options"):
                merged[q["number"]] = q

    questions_raw = list(merged.values())
    test_id = re.sub(r"[^a-zA-Z0-9_\-]+", "-", normalized_name_hint).strip("-").lower() or "uploaded"
    questions = _attach_answers(test_id, questions_raw, answers)
    questions = [
        q for q in questions if isinstance(q.get("number"), int) and 1 <= q["number"] <= 100
    ]
    questions = sorted(questions, key=lambda q: q["number"])
    display_name = normalized_name_hint.title()
    return {
        "id": test_id,
        "name": display_name,
        "description": description_hint or f"Parsed from {normalized_name_hint}",
        "questions": questions,
    }


_CACHE: Dict[str, Any] = {"stamp": 0.0, "tests": {}, "files": []}
# Session-scoped uploaded tests and missed-question tracking
_SESSION_UPLOADS: Dict[str, Dict[str, Any]] = {}
_MISSED_BY_SESSION: Dict[str, Dict[str, List[str]]] = {}


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


def _ensure_session_id() -> str:
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
        session.modified = True
    return sid


def _get_session_tests() -> Dict[str, Dict[str, Any]]:
    sid = _ensure_session_id()
    return _SESSION_UPLOADS.get(sid, {})


def _get_all_tests_for_session() -> Dict[str, Dict[str, Any]]:
    tests = dict(load_all_tests())
    session_tests = _get_session_tests()
    tests.update(session_tests)
    return tests


def _get_test_or_404(test_id: str) -> Dict[str, Any]:
    tests = _get_all_tests_for_session()
    test = tests.get(test_id)
    if not test:
        abort(404, description="Test not found")
    return test


def _get_question_or_404(test: Dict[str, Any], question_id: str) -> Dict[str, Any]:
    for question in test["questions"]:
        if question["id"] == question_id:
            return question
    abort(404, description="Question not found")


def _serialize_question_payload(question: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": question["id"],
        "question": question["question"],
        "options": question["options"],
        "number": question.get("number"),
    }


def get_incorrect_questions(test: Dict[str, Any], results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter a result list for incorrect answers and return sanitized questions."""
    question_map = {q["id"]: q for q in test.get("questions", [])}
    missed: List[Dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        if item.get("correct") is not False:
            continue
        qid = item.get("question_id")
        if qid in question_map:
            missed.append(_serialize_question_payload(question_map[qid]))
    return missed


def _get_missed_map() -> Dict[str, List[str]]:
    sid = _ensure_session_id()
    return _MISSED_BY_SESSION.setdefault(sid, {})


def _select_questions_for_mode(
    test: Dict[str, Any], mode: str = "regular", count: Optional[int] = None
) -> List[Dict[str, Any]]:
    questions = list(test["questions"])
    if mode == "review_incorrect":
        missed_map = _get_missed_map()
        missed_ids = set(missed_map.get(test["id"], []))
        if not missed_ids:
            return []
        questions = [q for q in questions if q["id"] in missed_ids]
    if count and count > 0:
        questions = questions[: min(count, len(questions), MAX_QUESTIONS_PER_RUN)]
    return [_serialize_question_payload(q) for q in questions]


@app.route("/")
def home():
    return render_template("index.html", default_random_order=DEFAULT_RANDOM_ORDER)


@app.route("/settings")
def settings():
    # Keep a single-page experience; direct /settings visits jump to the hash route.
    return redirect(f"{url_for('home')}#/settings", code=302)


@app.route("/api/tests")
def list_tests():
    tests = _get_all_tests_for_session()
    payload = []
    for test in tests.values():
        payload.append(
            {
                "id": test["id"],
                "name": test["name"],
                "description": test.get("description", ""),
                "question_count": len(test["questions"]),
            }
        )
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
                desired = min(desired, len(questions), MAX_QUESTIONS_PER_RUN)
                questions = questions[:desired]
        except ValueError:
            pass
    sanitized = [_serialize_question_payload(q) for q in questions]
    return jsonify(
        {
            "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
            "questions": sanitized,
            "selected_count": len(sanitized),
        }
    )


@app.route("/api/upload_pdf", methods=["POST"])
def upload_pdf():
    """Upload a PDF and store it only for the current session (no shared disk usage)."""
    file = request.files.get("file")
    if not file:
        abort(400, description="No file provided.")
    data = file.read()
    if not data:
        abort(400, description="Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        abort(413, description=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB).")

    try:
        parsed = _parse_uploaded_pdf(data, file.filename)
    except Exception as exc:
        abort(400, description=f"Could not parse PDF: {exc}")
    if not parsed or not parsed.get("questions"):
        abort(400, description="No questions found in this PDF.")

    sid = _ensure_session_id()
    unique_id = f"u-{sid}-{uuid.uuid4().hex}"
    parsed["id"] = unique_id
    parsed["description"] = parsed.get("description") or f"Uploaded by you ({file.filename})"
    _SESSION_UPLOADS.setdefault(sid, {})[unique_id] = parsed

    return jsonify(
        {
            "id": parsed["id"],
            "name": parsed["name"],
            "description": parsed.get("description", ""),
            "question_count": len(parsed.get("questions", [])),
        }
    )


@app.route("/api/tests/<test_id>/start_quiz", methods=["POST"])
def start_quiz(test_id: str):
    test = _get_test_or_404(test_id)
    payload = request.get_json(silent=True) or {}
    raw_count = payload.get("count")
    try:
        count = int(raw_count) if raw_count is not None else None
        if count is not None and count < 0:
            count = None
    except (TypeError, ValueError):
        count = None
    mode = payload.get("mode", "regular")
    if mode not in {"regular", "review_incorrect"}:
        mode = "regular"
    questions = _select_questions_for_mode(test, mode, count=count)
    if not questions:
        if mode == "review_incorrect":
            abort(400, description="No missed questions recorded yet for this test.")
        abort(400, description="No questions available for this request.")
    try:
        time_limit_seconds = int(payload.get("time_limit_seconds", 0))
        if time_limit_seconds < 0:
            time_limit_seconds = 0
        max_seconds = max(0, MAX_TIME_LIMIT_MINUTES * 60)
        if max_seconds:
            time_limit_seconds = min(time_limit_seconds, max_seconds)
    except (TypeError, ValueError):
        time_limit_seconds = 0
    return jsonify(
        {
            "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
            "questions": questions,
            "selected_count": len(questions),
            "mode": mode,
            "time_limit_seconds": time_limit_seconds,
        }
    )


@app.route("/api/tests/<test_id>/review_missed")
def review_missed(test_id: str):
    test = _get_test_or_404(test_id)
    missed_map = _get_missed_map()
    missed_for_test = missed_map.get(test_id, [])
    raw_count = request.args.get("count")
    try:
        count = int(raw_count) if raw_count else None
    except (TypeError, ValueError):
        count = None
    questions = _select_questions_for_mode(test, mode="review_incorrect", count=count)
    if not questions or not missed_for_test:
        abort(404, description="No missed questions stored for this test yet.")
    return jsonify(
        {
            "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
            "questions": questions,
            "selected_count": len(questions),
            "mode": "review_incorrect",
            "time_limit_seconds": 0,
        }
    )


@app.route("/api/tests/<test_id>/results", methods=["POST"])
def store_results(test_id: str):
    test = _get_test_or_404(test_id)
    missed_map = _get_missed_map()
    payload = request.get_json(silent=True) or {}
    results = payload.get("results")
    if not isinstance(results, list):
        abort(400, description="'results' must be a list.")
    missed_questions = get_incorrect_questions(test, results)
    missed_map[test["id"]] = [item["id"] for item in missed_questions]
    return jsonify({"missed_count": len(missed_questions)})


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


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))  # Replit sets PORT; fallback 8080 for local
    app.run(host=host, port=port, debug=False)
