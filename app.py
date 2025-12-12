import io
import json
import os
import re
import tempfile
import uuid
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, IO

from flask import Flask, jsonify, render_template, request, abort, redirect, url_for, session
from pypdf import PdfReader
from werkzeug.exceptions import HTTPException

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent.resolve()
TESTS_DIR = BASE_DIR / "tests"
INSTANCE_DIR = BASE_DIR / "instance"
SESSION_DATA_DIR = INSTANCE_DIR / "sessions"

# Ensure directories exist
TESTS_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DATA_DIR.mkdir(parents=True, exist_ok=True)

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


# --- TEXT PROCESSING UTILITIES ---

def _normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace and trim, but be careful not to merge words."""
    if not isinstance(text, str):
        return ""
    # Only fix very specific broken suffixes common in PDF extraction
    # patterns like "manage ment" -> "management"
    text = re.sub(r"\b(\w+)\s+(ment|tion|ing|able|ible|ness)\b", r"\1\2", text)
    # Collapse multiple spaces/newlines into one
    return re.sub(r"\s+", " ", text).strip()


def _strip_leading_number(text: str) -> str:
    """Remove leading markers like '12.' or 'A)'."""
    return re.sub(r"^\s*(?:\d{1,3}[).:\-]|[A-E][).:\-])\s*", "", text).strip()


# --- ERROR HANDLERS ---

@app.errorhandler(HTTPException)
def _json_http_error(exc: HTTPException):
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
    if isinstance(exc, HTTPException):
        return _json_http_error(exc)
    if request.path.startswith("/api/"):
        app.logger.exception("Unhandled error during API request")
        return jsonify({"error": "Internal Server Error", "description": str(exc)}), 500
    raise exc


# --- PDF PARSING ENGINE ---

def _looks_like_header_line(text: str) -> bool:
    """Detect lines that are likely running headers/footers."""
    patterns = [
        r"(?i)\bcluster\b",
        r"(?i)\bcareer\s+cluster\b",
        r"(?i)\btest\s*(number|#)\b",
        r"(?i)\bdeca\b",
        r"(?i)\bexam\b",
        r"(?i)^page\s+\d+",
        r"^\d+\s*(of|/)\s*\d+$",
        r"(?i)copyright",
    ]
    if any(re.search(p, text) for p in patterns):
        return True
    # Heuristic: Uppercase lines with few words are often section headers
    tokens = text.split()
    if len(tokens) >= 3 and all(tok.isupper() or re.fullmatch(r"[A-Z0-9\-]+", tok) for tok in tokens):
        return True
    return False

def _extract_clean_lines(source: Path | IO[bytes]) -> List[str]:
    """Read PDF, remove headers/footers, and return a clean list of lines."""
    reader = PdfReader(source)
    lines: List[str] = []

    # Regex to find embedded Questions (1. ) or Options (A. ) preceded by 2+ spaces
    # We look for "  1. " or "  A. "
    # We use a lookahead to keep the number/letter in the new line
    # NOTE: Use non-capturing group (?:...) inside lookahead so re.split doesn't return the match
    splitter = re.compile(r"\s{2,}(?=(?:\d{1,3}|[A-E])\s*[.:\-])")

    for page in reader.pages:
        raw_text = page.extract_text() or ""
        for raw_line in raw_text.splitlines():
            # First, attempt to split combined lines (e.g. "Copyright ... 76. Question ... A. Option")
            # We do this BEFORE stripping or collapsing spaces, as we rely on the spaces.
            if splitter.search(raw_line):
                parts = splitter.split(raw_line)
            else:
                parts = [raw_line]
                
            for line in parts:
                line = line.strip()
                if not line:
                    continue
                
                # NOW we can normalize internal spaces for this segment
                line = re.sub(r"\s{2,}", " ", line)
                
                # Skip obvious noise
                if _looks_like_header_line(line):
                    # Try to rescue content from mixed lines (e.g. "Copyright ... 76. Question")
                    # Common pattern: Copyright ... Ohio  <Number>.
                    # We strip the copyright part if it exists
                    cleaned = re.sub(r"(?i)^.*?copyright.*?ohio\s*", "", line)
                    if cleaned and cleaned != line:
                        line = cleaned
                        # Re-check if it looks like a header (e.g. just page number remaining)
                        if _looks_like_header_line(line):
                             continue
                    else:
                        continue
                    
                lines.append(line)
            
    # Remove duplicates that occur exactly every X lines (page headers)
    # This is a simple frequency filter for lines that appear on >50% of the pages (heuristic)
    # but strictly suppressing widely repeated lines like "Marketing Cluster Exam"
    counts = {}
    for l in lines:
        counts[l] = counts.get(l, 0) + 1
    
    threshold = max(2, len(reader.pages) // 2)
    final_lines = [l for l in lines if counts[l] < threshold and not _looks_like_header_line(l)]
    return final_lines

def _parse_answer_key(lines: List[str]) -> Dict[int, Dict[str, str]]:
    """Scan for the answer key section and parse it."""
    # Find start of answer key
    start_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if re.search(r"answer\s*(key|section)", lines[i], re.IGNORECASE):
            start_idx = i
            break
    
    # If not found, look for just "KEY" on a line by itself
    if start_idx == -1:
         for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().upper() == "KEY":
                start_idx = i
                break

    # If still not found, search for the first occurrence of "1. X" to guess start
    if start_idx == -1:
        # Scan last 60% of parsing just to be safe (answer keys usually in back half)
        # But for 2017.pdf it starts at ~38% (573/1497). So let's search entire file backwards or forwards?
        # Searching forwards from a reasonable midpoint (30%) might be safer.
        search_start = int(len(lines) * 0.3)
        pat_start = re.compile(r"^\s*1[\s.:]+[A-E]\b", re.IGNORECASE)
        for i in range(search_start, len(lines)):
             if pat_start.search(lines[i]):
                 start_idx = i
                 break

    # If still not found, fallback to 80%
    if start_idx == -1:
        start_idx = max(0, int(len(lines) * 0.8))

    answers = {}
    
    # Pattern: "1. A" or "1 A" or "1.A" followed by optional explanation
    # We look for a number at the start of a logical entry
    # This regex matches the start of an answer line: digit + char
    pattern = re.compile(r"(?<!\d)(\d{1,3})\s*[:.\-)]?\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    
    # We iterate and capture multi-line explanations
    i = start_idx
    while i < len(lines):
        match = pattern.search(lines[i])
        if match:
            num = int(match.group(1))
            let = match.group(2).upper()
            expl = match.group(3).strip()
            i += 1
            # Slurp lines until next answer number
            while i < len(lines):
                if pattern.search(lines[i]) or _looks_like_header_line(lines[i]):
                    break
                expl += " " + lines[i].strip()
                i += 1
            if 1 <= num <= 100:
                answers[num] = {"letter": let, "explanation": expl}
        else:
            i += 1
            
    return answers


def _smart_parse_questions(lines: List[str], answers: Dict[int, Any]) -> List[Dict[str, Any]]:
    """
    State-machine parser that consumes lines and identifies:
    - New Question (starts with Number)
    - Option (starts with A-E)
    - Continuation of previous text
    """
    
    questions = []
    current_q = None
    
    # Regexes
    # Start of a question: "1." or "10."
    q_start_re = re.compile(r"^(\d{1,3})\s*[).:\-]\s+(.*)")
    # Start of a option: "A." or "(A)"
    opt_start_re = re.compile(r"^\s*([A-E])\s*[).:\-]\s*(.*)")
    # Inline option splitter: captures " B. Next text" inside a line
    inline_opt_re = re.compile(r"(?<!\w)([A-E])\s*[).:\-]\s+")

    def finalize_current():
        nonlocal current_q
        if current_q:
            # Clean up
            current_q["prompt"] = _normalize_whitespace(current_q["prompt"])
            for opt in current_q["options"]:
                opt["text"] = _normalize_whitespace(opt["text"])
            questions.append(current_q)
        current_q = None

    for line in lines:
        # Check for answer key start - stop parsing questions if found
        if re.search(r"answer\s*(key|section)", line, re.IGNORECASE):
            break

        # 1. Is it a new question?
        q_match = q_start_re.match(line)
        if q_match:
            finalize_current()
            num = int(q_match.group(1))
            text = q_match.group(2)
            current_q = {
                "number": num,
                "prompt": text,
                "options": []
            }
            # Check for inline options in the prompt line
            # e.g. "1. What is X? A. This B. That"
            # We rarely see this in these PDFs, but good to handle
            continue

        if not current_q:
            continue

        # 2. Is it a new option?
        opt_match = opt_start_re.match(line)
        if opt_match:
            label = opt_match.group(1).upper()
            text = opt_match.group(2)
            current_q["options"].append({"label": label, "text": text})
            
            # Check compatibility with inline options on the SAME line
            # e.g. "A. Option 1  B. Option 2"
            # We split by looking for other [A-E]. markers
            split_iter = list(inline_opt_re.finditer(text))
            if split_iter:
                # We have multiple options on this line. Rewind and split properly.
                # Actually, simpler: just take the text we just found and split it
                # The first one is already added, but its text contains the others.
                # Let's fix the last option added
                full_text = text
                # Re-split
                parts = re.split(inline_opt_re, full_text) # ['First part', 'B', 'Second part', 'C', ...]
                # parts[0] is the text for the current label
                current_q["options"][-1]["text"] = parts[0]
                
                # The rest come in pairs: Label, Text
                idx = 1
                while idx < len(parts) - 1:
                    lbl = parts[idx].strip().upper()
                    val = parts[idx+1].strip()
                    current_q["options"].append({"label": lbl, "text": val})
                    idx += 2
            continue

        # 3. Continuation line
        # If we have options, append to the last option
        if current_q["options"]:
            # Guard: check if this line looks like a question number but was missed
            # (Strict check to avoid merging next question into previous option)
            if re.match(r"^\d{1,3}\.", line):
                finalize_current()
                # Reprocess this line as a new question
                # (Recursion or simple loop reset would be better, but for simplicity
                # we just treat it as a new start if strictly matching)
                q_match_retry = q_start_re.match(line)
                if q_match_retry:
                     num = int(q_match_retry.group(1))
                     text = q_match_retry.group(2)
                     current_q = {"number": num, "prompt": text, "options": []}
                continue

            current_q["options"][-1]["text"] += " " + line
        else:
            # Append to prompt
            current_q["prompt"] += " " + line

    finalize_current()
    
    # --- MERGE WITH ANSWERS ---
    
    final_questions = []
    seen_ids = set()
    
    for q in questions:
        num = q["number"]
        if num in seen_ids: continue
        
        ans_data = answers.get(num)
        ans_letter = ans_data["letter"] if ans_data else None
        explanation = ans_data["explanation"] if ans_data else ""
        
        # Determine correct index
        correct_idx = None
        if ans_letter:
            for i, opt in enumerate(q["options"]):
                if opt["label"] == ans_letter:
                    correct_idx = i
                    break
        
        # Fallback if text extraction failed to grab options properly but we know the answer
        if correct_idx is None and ans_letter:
            idx_guess = ord(ans_letter) - ord('A')
            if 0 <= idx_guess < 5:
                # If we have enough options, assume positional match
                if idx_guess < len(q["options"]):
                    correct_idx = idx_guess
        
        # Generate ID
        q_id = f"q-{num}"
        
        final_questions.append({
            "id": q_id,
            "number": num,
            "question": q["prompt"],
            "options": [o["text"] for o in q["options"]],
            "correct_index": correct_idx if correct_idx is not None else 0,
            "correct_letter": ans_letter if ans_letter else "?",
            "explanation": explanation if explanation else "No explanation available (Parse failed)"
        })
        seen_ids.add(num)
        
    return final_questions


def _parse_pdf_source(source: Path | IO[bytes], name_hint: str) -> Dict[str, Any]:
    """Single robust entry point for parsing."""
    try:
        lines = _extract_clean_lines(source)
        answers = _parse_answer_key(lines)
        questions = _smart_parse_questions(lines, answers)
        
        # Sort by number
        questions.sort(key=lambda x: x["number"])
        
        test_id = re.sub(r"[^a-z0-9]+", "-", name_hint.lower()).strip("-")
        # Ensure unique IDs for the test scope
        for q in questions:
            q["id"] = f"{test_id}-q{q['number']}"

        return {
            "id": test_id,
            "name": name_hint,
            "description": f"Parsed {len(questions)} questions.",
            "questions": questions
        }
    except Exception as e:
        print(f"Parsing error: {e}")
        return {}


# --- PERSISTENCE LAYER (FILESYSTEM) ---

def _get_session_id() -> str:
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]

def _get_session_file_path(sid: str) -> Path:
    return SESSION_DATA_DIR / f"{sid}.json"

def _load_session_data(sid: str) -> Dict[str, Any]:
    path = _get_session_file_path(sid)
    if not path.exists():
        return {"uploads": {}, "missed": {}}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {"uploads": {}, "missed": {}}

def _save_session_data(sid: str, data: Dict[str, Any]):
    path = _get_session_file_path(sid)
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Failed to save session: {e}")

def _get_all_tests_for_session() -> Dict[str, Any]:
    # 1. Load disk tests (global)
    all_tests = {}
    
    # Simple cache to avoid re-parsing disk PDFs every request
    #In a real app, use a proper cache. Here we just scan quickly.
    # Actually, let's re-implement `load_all_tests` correctly using the new parser
    # cache it in a global for read-only static files
    global _STATIC_TESTS_CACHE
    if not _STATIC_TESTS_CACHE:
        for p in tests_dir_iter():
            parsed = _parse_pdf_source(p, p.stem)
            if parsed and parsed.get("questions"):
                _STATIC_TESTS_CACHE[parsed["id"]] = parsed
    
    all_tests.update(_STATIC_TESTS_CACHE)
    
    # 2. Load session uploads
    sid = _get_session_id()
    s_data = _load_session_data(sid)
    all_tests.update(s_data.get("uploads", {}))
    
    return all_tests

def tests_dir_iter():
    try:
        return TESTS_DIR.glob("*.pdf")
    except:
        return []

_STATIC_TESTS_CACHE = {}


# --- ROUTES ---

@app.route("/")
def home():
    return render_template("index.html", default_random_order=DEFAULT_RANDOM_ORDER)

@app.route("/settings")
def settings():
    return redirect(f"{url_for('home')}#/settings", code=302)

@app.route("/api/tests")
def list_tests():
    data = _get_all_tests_for_session()
    payload = []
    for t in data.values():
        payload.append({
            "id": t["id"],
            "name": t["name"],
            "description": t.get("description", ""),
            "question_count": len(t.get("questions", []))
        })
    return jsonify(payload)

@app.route("/api/tests/<test_id>/questions")
def get_questions(test_id):
    all_t = _get_all_tests_for_session()
    test = all_t.get(test_id)
    if not test:
        abort(404, "Test not found")
        
    qs = test["questions"]
    count = request.args.get("count", type=int)
    if count and count > 0:
        qs = qs[:min(count, MAX_QUESTIONS_PER_RUN)]
        
    # Serialize
    return jsonify({
        "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
        "questions": qs,
        "selected_count": len(qs)
    })

@app.route("/api/tests/<test_id>/start_quiz", methods=["POST"])
def start_quiz(test_id):
    all_t = _get_all_tests_for_session()
    test = all_t.get(test_id)
    if not test:
        abort(404, "Test not found")
        
    payload = request.json or {}
    mode = payload.get("mode", "regular")
    count = payload.get("count")
    
    questions = test["questions"]
    
    if mode == "review_incorrect":
        sid = _get_session_id()
        s_data = _load_session_data(sid)
        missed_ids = set(s_data.get("missed", {}).get(test_id, []))
        questions = [q for q in questions if q["id"] in missed_ids]
        if not questions:
            abort(400, "No missed questions recording for this test.")
            
    if count and isinstance(count, int) and count > 0:
        questions = questions[:min(count, MAX_QUESTIONS_PER_RUN)]
        
    try:
        limit = int(payload.get("time_limit_seconds", 0))
    except:
        limit = 0
        
    return jsonify({
        "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
        "questions": questions,
        "selected_count": len(questions),
        "mode": mode,
        "time_limit_seconds": limit
    })

@app.route("/api/upload_pdf", methods=["POST"])
def upload_pdf():
    f = request.files.get("file")
    if not f: abort(400, "No file")
    
    raw = f.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        abort(413, "Too large")
        
    parsed = _parse_pdf_source(io.BytesIO(raw), f.filename.replace(".pdf", ""))
    if not parsed or not parsed.get("questions"):
        abort(400, "Could not parse questions from PDF")
        
    # Inject session-specific ID
    sid = _get_session_id()
    # Unique ID for this specific upload to prevent collisions
    uid = f"u-{uuid.uuid4().hex[:8]}"
    parsed["id"] = uid
    parsed["name"] = f.filename
    
    # Update question IDs to match the test ID
    for q in parsed["questions"]:
        q["id"] = f"{uid}-q{q['number']}"
    
    # Save to disk
    data = _load_session_data(sid)
    # Enforce single upload: Clear previous uploads
    data["uploads"] = {}
    data["uploads"][uid] = parsed
    _save_session_data(sid, data)
    
    return jsonify({
        "id": uid,
        "name": parsed["name"],
        "question_count": len(parsed["questions"])
    })

@app.route("/api/tests/<test_id>/check/<question_id>", methods=["POST"])
def check_answer(test_id, question_id):
    # This endpoint is stateless logic, we just need the correct index
    # But we need the test data to know the correct index
    all_t = _get_all_tests_for_session()
    test = all_t.get(test_id)
    if not test: abort(404, "Test not found")
    
    q = next((x for x in test["questions"] if x["id"] == question_id), None)
    if not q: abort(404, "Question not found")
    
    choice = request.json.get("choice")
    if choice is None: abort(400, "Choice required")
    
    is_correct = (choice == q["correct_index"])
    return jsonify({"correct": is_correct})

@app.route("/api/tests/<test_id>/results", methods=["POST"])
def store_results(test_id):
    sid = _get_session_id()
    results = request.json.get("results", [])
    if not results: return jsonify({"missed_count": 0})
    
    # Identify missed IDs
    missed_ids = []
    for r in results:
        if r.get("correct") is False:
            missed_ids.append(r.get("question_id"))
            
    # Persist
    data = _load_session_data(sid)
    if "missed" not in data: data["missed"] = {}
    
    # Overwrite misted list for this test? Or append? 
    # Usually we want the latest set of missed questions to review
    data["missed"][test_id] = missed_ids
    _save_session_data(sid, data)
    
    return jsonify({"missed_count": len(missed_ids)})

@app.route("/api/tests/<test_id>/answer/<question_id>")
def get_answer_details(test_id, question_id):
    all_t = _get_all_tests_for_session()
    test = all_t.get(test_id)
    if not test: abort(404)
    q = next((x for x in test["questions"] if x["id"] == question_id), None)
    if not q: abort(404)
    
    return jsonify({
        "correct_index": q["correct_index"],
        "correct_letter": q["correct_letter"],
        "explanation": q["explanation"]
    })

if __name__ == "__main__":
    app.run(debug=True, port=8080)
