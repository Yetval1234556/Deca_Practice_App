import io
import json
import os
import re
import random
import tempfile
import uuid
import shutil
import time
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, IO

from flask import Flask, jsonify, render_template, request, abort, redirect, url_for, session
from pypdf import PdfReader
from werkzeug.exceptions import HTTPException

BASE_DIR = Path(__file__).parent.resolve()
TESTS_DIR = BASE_DIR / "tests"
INSTANCE_DIR = BASE_DIR / "instance"
SESSION_DATA_DIR = INSTANCE_DIR / "sessions"

try:
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    print("⚠️  WARNING: Could not create TESTS_DIR. Uploads might fail if not using /tmp.")

try:
    SESSION_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    
    print("⚠️  WARNING: Read-only filesystem detected. Using /tmp for sessions.")
    SESSION_DATA_DIR = Path(tempfile.gettempdir()) / "deca_app_sessions"
    SESSION_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_QUESTIONS_PER_RUN = int(os.getenv("MAX_QUESTIONS_PER_RUN", "100"))
MAX_TIME_LIMIT_MINUTES = int(os.getenv("MAX_TIME_LIMIT_MINUTES", "180"))
DEFAULT_RANDOM_ORDER = os.getenv("DEFAULT_RANDOM_ORDER", "false").lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "12582912"))
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("ENVIRONMENT") == "production":
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        print("⚠️  WARNING: SECRET_KEY not set in production. Generated temporary key.")
    else:
        SECRET_KEY = "dev-secret-key"
        print("⚠️  WARNING: Using default SECRET_KEY in development")
SESSION_CLEANUP_AGE_SECONDS = 86400

DB_PATH = INSTANCE_DIR / "sessions.db"

def _init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT, updated_at REAL)")
            conn.commit()
    except Exception as e:
        print(f"⚠️  DB Init Failed: {e}")

_init_db()  

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_TYPE="filesystem",
)

def _normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    
    
    
    for _ in range(3):
         
         text = re.sub(r"\b([b-hj-zB-HJ-Z])\s+([a-zA-Z])", r"\1\2", text)
         
    text = re.sub(r"\b(\w+)\s+(ment|tion|ing|able|ible|ness)\b", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()

def _strip_leading_number(text: str) -> str:
    return re.sub(r"^\s*(?:\d{1,3}[).:\-]|[A-E][).:\-])\s*", "", text).strip()

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

def _looks_like_header_line(text: str) -> bool:
    patterns = [
        r"(?i)\bcluster\b",
        r"(?i)\bcareer\s+cluster\b",
        r"(?i)\btest\s*(number|#)\b",
        r"(?i)\bdeca\b",
        r"(?i)\bexam\b",
        r"(?i)^page\s+\d+",
        r"^\d+\s*(of|/)\s*\d+$",
        r"(?i)copyright",
        r"^[A-Z]{3,4}\s+-\s+[A-Z]", 
    ]
    if any(re.search(p, text) for p in patterns):
        return True
    tokens = text.split()
    if len(tokens) >= 3 and all(tok.isupper() or re.fullmatch(r"[A-Z0-9\-]+", tok) for tok in tokens):
        return True
    return False

def _extract_clean_lines(source: Path | IO[bytes]) -> List[str]:
    reader = PdfReader(source)
    lines: List[str] = []

    splitter = re.compile(r"\s{2,}(?=(?:\d{1,3}|[A-E])\s*[.:\-])")

    for page in reader.pages:
        raw_text = page.extract_text() or ""
        for raw_line in raw_text.splitlines():
            if splitter.search(raw_line):
                parts = splitter.split(raw_line)
            else:
                parts = [raw_line]
                
            for line in parts:
                line = line.strip()
                if not line:
                    continue
                
                line = re.sub(r"\s{2,}", " ", line)

                
                
                
                
                footer_regex = re.compile(r"(?:^|\s+)\b([A-Z]{3,5}\s*[-–—]\s*[A-Z])")
                footer_match = footer_regex.search(line)
                if footer_match:
                     line = line[:footer_match.start()].strip()
                     
                     line = re.sub(r"\s+(and|Cluster)$", "", line).strip()
                     line = re.sub(r"\s+(Business Management|Hospitality|Finance|Marketing|Entrepreneurship|Administration)\s*$", "", line).strip()
                
                
                if "specialist levels." in line:
                    line = line.replace("specialist levels.", "").strip()
                if "Center®, Columbus, Ohio" in line:
                     line = line.split("Center®, Columbus, Ohio")[0].strip()
                if "career -sustaining" in line:
                    line = line.split("career -sustaining")[0].strip()
                if line.endswith("Business Management and"):
                    line = line[:-23].strip() 
                if "sustaining, specialist, supervi" in line:
                    line = line.split("sustaining, specialist, supervi")[0].strip()
                
                if _looks_like_header_line(line):
                    cleaned = re.sub(r"(?i)^.*?copyright.*?ohio\s*", "", line)
                    if cleaned and cleaned != line:
                        line = cleaned
                        if _looks_like_header_line(line):
                             continue
                    else:
                        continue
                    
                lines.append(line)
            
    counts = {}
    for l in lines:
        counts[l] = counts.get(l, 0) + 1
    
    threshold = max(2, len(reader.pages) // 2)
    final_lines = [l for l in lines if counts[l] < threshold and not _looks_like_header_line(l)]
    return final_lines

def _parse_answer_key(lines: List[str]) -> Dict[int, Dict[str, str]]:
    start_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if re.search(r"answer\s*(key|section)", lines[i], re.IGNORECASE):
            start_idx = i
            break
    
    if start_idx == -1:
         for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().upper() == "KEY":
                start_idx = i
                break

    if start_idx == -1:
        search_start = int(len(lines) * 0.3)
        pat_start = re.compile(r"^\s*1[\s.:]+[A-E]\b", re.IGNORECASE)
        for i in range(search_start, len(lines)):
             if pat_start.search(lines[i]):
                 start_idx = i
                 break

    if start_idx == -1:
        start_idx = max(0, int(len(lines) * 0.8))

    answers = {}
    
    pattern = re.compile(r"(?<!\d)(\d{1,3})\s*[:.\-)]?\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    
    i = start_idx
    while i < len(lines):
        match = pattern.search(lines[i])
        if match:
            num = int(match.group(1))
            let = match.group(2).upper()
            expl = match.group(3).strip()
            i += 1
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
    questions = []
    current_q = None
    
    q_start_re = re.compile(r"^(\d{1,3})\s*[).:\-]\s+(.*)")
    opt_start_re = re.compile(r"^\s*([A-E])\s*[).:\-]\s*(.*)")
    inline_opt_re = re.compile(r"(?<!\w)([A-E])\s*[).:\-]\s+")

    def finalize_current():
        nonlocal current_q
        if current_q:
            current_q["prompt"] = _normalize_whitespace(current_q["prompt"])
            for opt in current_q["options"]:
                opt["text"] = _normalize_whitespace(opt["text"])
            questions.append(current_q)
        current_q = None

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        
        
        if line.lower().strip() == "answer key":
             break

        
        q_match = q_start_re.match(line)
        if q_match:
            num = int(q_match.group(1))
            if not (1 <= num <= 100):
                continue
                
            finalize_current()
            text = q_match.group(2)
            current_q = {
                "number": num,
                "prompt": text,
                "options": []
            }
            continue

        
        opt_match = opt_start_re.match(line)
        if opt_match:
            label = opt_match.group(1).upper()
            text = opt_match.group(2)
            
            
            if not text.strip() and i < len(lines):
                 
                 next_line = lines[i]
                 
                 if not opt_start_re.match(next_line) and not q_start_re.match(next_line):
                      text = next_line
                      i += 1
            
            
            
            if current_q and label == "A" and any(o["label"] == "A" for o in current_q["options"]):
                prev_num = current_q["number"]
                finalize_current()
                
                current_q = {
                    "number": prev_num + 1,
                    "prompt": "[Prompt text missing from PDF]",
                    "options": []
                }
            
            if not current_q:
                
                
                if label == "A" and not questions:
                    current_q = {
                        "number": 1,
                        "prompt": "[Question prompt missing from PDF text]",
                        "options": []
                    }
                else:
                    
                    continue

            current_q["options"].append({"label": label, "text": text})
            
            
            split_iter = list(inline_opt_re.finditer(text))
            if split_iter:
                full_text = text
                
                parts = re.split(inline_opt_re, full_text)
                current_q["options"][-1]["text"] = parts[0]
                
                idx = 1
                while idx < len(parts) - 1:
                    lbl = parts[idx].strip().upper()
                    val = parts[idx+1].strip()
                    current_q["options"].append({"label": lbl, "text": val})
                    idx += 2
            continue

        if current_q:
            if current_q["options"]:
                if re.match(r"^\d{1,3}\.", line):
                    finalize_current()
                    q_match_retry = q_start_re.match(line)
                    if q_match_retry:
                         num = int(q_match_retry.group(1))
                         text = q_match_retry.group(2)
                         current_q = {"number": num, "prompt": text, "options": []}
                    continue
    
                current_q["options"][-1]["text"] += " " + line
            else:
                current_q["prompt"] += " " + line

    finalize_current()

    final_questions = []
    seen_ids = set()
    
    for q in questions:
        num = q["number"]
        if num in seen_ids: continue
        
        
        q["options"].sort(key=lambda x: x["label"])
        
        
        labels = [o["label"] for o in q["options"]]
        if labels:
            
            expected_labels = ['A','B','C','D','E']
            
            max_idx = -1
            for l in labels:
                if l in expected_labels:
                    max_idx = max(max_idx, expected_labels.index(l))
            
            
            
            
            target_count = max(4, max_idx + 1)
            
            new_options = []
            current_src_idx = 0
            for i in range(target_count):
                exp_label = expected_labels[i]
                if current_src_idx < len(q["options"]) and q["options"][current_src_idx]["label"] == exp_label:
                    new_options.append(q["options"][current_src_idx])
                    current_src_idx += 1
                else:
                    
                    new_options.append({"label": exp_label, "text": "[Option missing from PDF]"})
            
            q["options"] = new_options
        else:
            
            q["options"] = [{"label": l, "text": "[Option missing]"} for l in "ABCD"]
        
        ans_data = answers.get(num)
        ans_letter = ans_data["letter"] if ans_data else None
        explanation = ans_data["explanation"] if ans_data else ""
        
        correct_idx = None
        if ans_letter:
            for i, opt in enumerate(q["options"]):
                if opt["label"] == ans_letter:
                    correct_idx = i
                    break
        
        if correct_idx is None and ans_letter:
            idx_guess = ord(ans_letter) - ord('A')
            if 0 <= idx_guess < 5:
                if idx_guess < len(q["options"]):
                    correct_idx = idx_guess
        
        q_id = f"q-{num}"
        
        final_questions.append({
            "id": q_id,
            "number": num,
            "question": q["prompt"],
            "options": [o["text"] for o in q["options"]],
            "correct_index": correct_idx if correct_idx is not None else -1,
            "correct_letter": ans_letter if ans_letter else "?",
            "explanation": explanation if explanation else "No explanation available (Parse failed)"
        })
        seen_ids.add(num)
        
    return final_questions

def _parse_pdf_source(source: Path | IO[bytes], name_hint: str) -> Dict[str, Any]:
    try:
        lines = _extract_clean_lines(source)
        answers = _parse_answer_key(lines)
        questions = _smart_parse_questions(lines, answers)
        
        questions.sort(key=lambda x: x["number"])
        
        test_id = re.sub(r"[^a-z0-9]+", "-", name_hint.lower()).strip("-")
        if not test_id:
            test_id = f"test-{uuid.uuid4().hex[:8]}"
            
        for q in questions:
            q["id"] = f"{test_id}-q{q['number']}"

        return {
            "id": test_id,
            "name": name_hint,
            "description": "",
            "questions": questions,
            "question_count": len(questions)
        }
    except Exception as e:
        
        app.logger.error(f"PDF parsing error for '{name_hint}': {e}", exc_info=True)
        print(f"⚠️  Parsing error for '{name_hint}': {e}")
        return {}

def _get_session_id() -> str:
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]

def _get_session_data_db(sid: str) -> Dict[str, Any]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data FROM sessions WHERE id = ?", (sid,))
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
    except Exception as e:
        app.logger.error(f"DB Read Error: {e}")
    return {"uploads": {}, "missed": {}}

def _save_session_data_db(sid: str, data: Dict[str, Any]):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO sessions (id, data, updated_at) VALUES (?, ?, ?)",
                         (sid, json.dumps(data), time.time()))
            conn.commit()
    except Exception as e:
        app.logger.error(f"DB Write Error: {e}")

def _load_session_data(sid: str) -> Dict[str, Any]:
    return _get_session_data_db(sid)

def _save_session_data(sid: str, data: Dict[str, Any]):
    _save_session_data_db(sid, data)

def _cleanup_old_sessions():
    """Removes sessions older than SESSION_CLEANUP_AGE_SECONDS."""
    try:
        limit_time = time.time() - SESSION_CLEANUP_AGE_SECONDS
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE updated_at < ?", (limit_time,))
            conn.commit()
    except Exception as e:
        print(f"Cleanup error: {e}")

def _get_all_tests_for_session() -> Dict[str, Any]:
    all_tests = {}
    
    global _STATIC_TESTS_CACHE
    if not _STATIC_TESTS_CACHE:
        for p in tests_dir_iter():
            parsed = _parse_pdf_source(p, p.stem)
            if parsed and parsed.get("questions"):
                _STATIC_TESTS_CACHE[parsed["id"]] = parsed
    
    all_tests.update(_STATIC_TESTS_CACHE)
    
    sid = _get_session_id()
    s_data = _load_session_data(sid)
    all_tests.update(s_data.get("uploads", {}))
    
    return all_tests

def tests_dir_iter():
    try:
        return TESTS_DIR.glob("*.pdf")
    except Exception as e:
        app.logger.warning(f"Failed to list tests directory: {e}")
        return []

_STATIC_TESTS_CACHE = {}

@app.route("/")
def home():
    
    if random.random() < 0.05:  
        _cleanup_old_sessions()
        
    sid = _get_session_id()
    
    _load_session_data(sid)
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
        if limit > MAX_TIME_LIMIT_MINUTES * 60:
            limit = MAX_TIME_LIMIT_MINUTES * 60
    except (ValueError, TypeError):
        limit = 0
        

    # Sanitize questions to remove answers
    sanitized_questions = []
    for q in questions:
        q_copy = q.copy()
        q_copy.pop("correct_index", None)
        q_copy.pop("correct_letter", None)
        q_copy.pop("explanation", None)
        sanitized_questions.append(q_copy)

    return jsonify({
        "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
        "questions": sanitized_questions,
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
        
    sid = _get_session_id()
    uid = f"u-{uuid.uuid4().hex[:8]}"
    parsed["id"] = uid
    parsed["name"] = f.filename
    
    for q in parsed["questions"]:
        q["id"] = f"{uid}-q{q['number']}"
    
    data = _load_session_data(sid)
    if "uploads" not in data:
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
    all_t = _get_all_tests_for_session()
    test = all_t.get(test_id)
    if not test: abort(404, "Test not found")
    
    q = next((x for x in test["questions"] if x["id"] == question_id), None)
    if not q: abort(404, "Question not found")
    
    if not request.json: abort(400, "JSON body required")
    choice = request.json.get("choice")
    if choice is None: abort(400, "Choice required")
    
    is_correct = (choice == q["correct_index"])
    return jsonify({"correct": is_correct})

@app.route('/api/search', methods=['GET'])
def search_questions():
    query = request.args.get('q', '').lower().strip()
    if not query or len(query) < 2:
        return jsonify([])

    results = []
    # Search all tests (static + session)
    all_tests = _get_all_tests_for_session()
    
    for test_id, test_data in all_tests.items():
        if not test_data.get("questions"):
            continue
        
        for q in test_data["questions"]:
            text = (q.get("question") or "").lower()
            if query in text:
                results.append({
                    "test_id": test_id,
                    "test_name": test_data.get("name"),
                    "question_id": q.get("id"),
                    "question_number": q.get("number"),
                    "snippet": q.get("question")[:150] + "..." if len(q.get("question")) > 150 else q.get("question"),
                })
                if len(results) >= 50: break
        if len(results) >= 50: break
            
    return jsonify(results)

@app.route("/api/tests/<test_id>/results", methods=["POST"])
def store_results(test_id):
    sid = _get_session_id()
    results = request.json.get("results", [])
    if not results: return jsonify({"missed_count": 0})
    
    missed_ids = []
    for r in results:
        if r and r.get("correct") is False:
            missed_ids.append(r.get("question_id"))
            
    data = _load_session_data(sid)
    if "missed" not in data: data["missed"] = {}
    
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
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)