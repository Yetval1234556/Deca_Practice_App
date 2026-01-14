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

# Ensure DB is in a writable location
DB_PATH = SESSION_DATA_DIR / "sessions.db"

def _init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT, updated_at REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS active_users (ip TEXT PRIMARY KEY, ua TEXT, last_seen REAL)")
            conn.commit()
        print(f"✅ Database initialized at {DB_PATH}")
    except Exception as e:
        print(f"❌ FATAL: Database initialization failed: {e}")
        print(f"Database path: {DB_PATH}")
        print("Application cannot continue without database.")
        import sys
        sys.exit(1)

_init_db()  

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_TYPE="filesystem",
)

import threading
def _background_cleanup():
    """Run cleanup periodically in background"""
    import time
    while True:
        time.sleep(3600)
        try:
            _cleanup_old_sessions()
        except Exception as e:
            print(f"Background cleanup error: {e}")

cleanup_thread = threading.Thread(target=_background_cleanup, daemon=True)
cleanup_thread.start()

def _normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    
    # Fix specific common broken words
    text = text.replace("SOURC E", "SOURCE")
    text = re.sub(r"\b(SOURC)\s+(E)\b", "SOURCE", text)

    text = re.sub(r"\b(\w+)\s+(ment|tion|ing|able|ible|ness)\b", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()

def _strip_leading_number(text: str) -> str:
    return re.sub(r"^\s*(?:\d{1,3}[).:\-]|[A-E][).:\-])\s*", "", text).strip()

@app.before_request
def track_active_user():
    try:
        # Support for proxies (Koyeb/Heroku/etc)
        # request.access_route[0] or X-Forwarded-For usually contains the real IP
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip and "," in ip:
            ip = ip.split(",")[0].strip()
            
        if ip:
            ua = request.headers.get("User-Agent", "Unknown")
            now = time.time()
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("INSERT OR REPLACE INTO active_users (ip, ua, last_seen) VALUES (?, ?, ?)",
                             (ip, ua, now))
                conn.commit()
    except Exception:
        pass  # Don't fail request if tracking fails

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
                
                # Handle copyright lines that may have answer key concatenated (e.g., "Ohio1.A")
                ohio_match = re.search(r"(Center®?,?\s*Columbus,?\s*Ohio)\s*(\d{1,3}\s*[.:,-]?\s*[A-E].*)?$", line, re.IGNORECASE)
                if ohio_match:
                    # Keep the answer part if present
                    answer_part = ohio_match.group(2)
                    line = line[:ohio_match.start()].strip()
                    if answer_part:
                        lines.append(answer_part.strip())
                
                if "career -sustaining" in line:
                    line = line.split("career -sustaining")[0].strip()
                if line.endswith("Business Management and"):
                    line = line[:-23].strip() 
                if "sustaining, specialist, supervi" in line:
                    line = line.split("sustaining, specialist, supervi")[0].strip()
                
                # Enhanced strict footer stripping
                line = re.sub(r"(?:^|\s+)Hospitality and Tourism.*$", "", line, flags=re.IGNORECASE).strip()
                line = re.sub(r"(?:^|\s+)Business Management.*$", "", line, flags=re.IGNORECASE).strip()
                line = re.sub(r"(?:^|\s+)\d{4}-\d{4}.*$", "", line).strip()
                line = re.sub(r"(?:^|\s+)Copyright.*$", "", line, flags=re.IGNORECASE).strip()
                
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

def _fix_broken_words(text: str) -> str:
    if not text: return ""
    
    # =========================================================================
    # 1. FIX COMMON SPLIT WORDS (highest impact - 140k+ fixes)
    # =========================================================================
    # These are the most common PDF extraction artifacts - comprehensive list
    common_fixes = [
        # === BUSINESS/FINANCE CORE TERMS ===
        (r'\bbusi?\s*ness\b', 'business'),
        (r'\bbus\s+iness\b', 'business'),
        (r'\bfi\s*nance\b', 'finance'),
        (r'\bfi\s*nan\s*cial\b', 'financial'),
        (r'\bin\s*for\s*ma\s*tion\b', 'information'),
        (r'\binfor\s*mation\b', 'information'),
        (r'\bman\s*age\s*ment\b', 'management'),
        (r'\bmanage\s*ment\b', 'management'),
        (r'\bcus\s*tom\s*er\b', 'customer'),
        (r'\bcustom\s*er\b', 'customer'),
        (r'\bcom\s*pa\s*ny\b', 'company'),
        (r'\bcompan\s*y\b', 'company'),
        (r'\bpro\s*duct\b', 'product'),
        (r'\bproduc\s*t\b', 'product'),
        (r'\bser\s*vice\b', 'service'),
        (r'\bservic\s*e\b', 'service'),
        (r'\bmar\s*ket\s*ing\b', 'marketing'),
        (r'\bmarket\s*ing\b', 'marketing'),
        (r'\bem\s*ploy\s*ee\b', 'employee'),
        (r'\bemploy\s*ee\b', 'employee'),
        (r'\bor\s*gan\s*iza\s*tion\b', 'organization'),
        (r'\borgan\s*ization\b', 'organization'),
        (r'\borganiza\s*tion\b', 'organization'),
        (r'\bcom\s*mu\s*ni\s*ca\s*tion\b', 'communication'),
        (r'\bcommunica\s*tion\b', 'communication'),
        (r'\bde\s*ci\s*sion\b', 'decision'),
        (r'\bdeci\s*sion\b', 'decision'),
        (r'\bop\s*er\s*a\s*tion\b', 'operation'),
        (r'\bopera\s*tion\b', 'operation'),
        
        # === COMMON VERBS ===
        (r'\bSOURC\s*E\b', 'SOURCE'),
        (r'\bsourc\s*e\b', 'source'),
        (r'\bre\s*triev\s*ed\b', 'retrieved'),
        (r'\bRetriev\s*ed\b', 'Retrieved'),
        (r'\bdeter\s*mine\b', 'determine'),
        (r'\bunder\s*stand\b', 'understand'),
        (r'\bunder\s*standing\b', 'understanding'),
        (r'\bpro\s*vide\b', 'provide'),
        (r'\bprovid\s*ing\b', 'providing'),
        (r'\bim\s*prove\b', 'improve'),
        (r'\bimprov\s*ing\b', 'improving'),
        (r'\bcon\s*sider\b', 'consider'),
        (r'\bcon\s*tact\b', 'contact'),
        (r'\bcon\s*trol\b', 'control'),
        (r'\bcon\s*tract\b', 'contract'),
        (r'\bcon\s*sumer\b', 'consumer'),
        (r'\bcon\s*tinue\b', 'continue'),
        (r'\bex\s*ample\b', 'example'),
        (r'\bex\s*plain\b', 'explain'),
        (r'\bex\s*pect\b', 'expect'),
        (r'\bex\s*perience\b', 'experience'),
        (r'\bre\s*quire\b', 'require'),
        (r'\bre\s*sponse\b', 'response'),
        (r'\bre\s*sult\b', 'result'),
        (r'\bre\s*port\b', 'report'),
        (r'\bre\s*ceive\b', 'receive'),
        (r'\bre\s*view\b', 'review'),
        (r'\bre\s*search\b', 'research'),
        (r'\bper\s*form\b', 'perform'),
        (r'\bper\s*son\b', 'person'),
        (r'\bper\s*sonal\b', 'personal'),
        
        # === COMMON NOUNS ===
        (r'\bprofes\s*sional\b', 'professional'),
        (r'\brel\s*ation\s*ship\b', 'relationship'),
        (r'\brelation\s*ship\b', 'relationship'),
        (r'\bdevel\s*op\s*ment\b', 'development'),
        (r'\bdevelop\s*ment\b', 'development'),
        (r'\benviron\s*ment\b', 'environment'),
        (r'\btech\s*nol\s*ogy\b', 'technology'),
        (r'\btechnol\s*ogy\b', 'technology'),
        (r'\badver\s*tis\s*ing\b', 'advertising'),
        (r'\badvertis\s*ing\b', 'advertising'),
        (r'\bexplan\s*ation\b', 'explanation'),
        (r'\binstru\s*ment\b', 'instrument'),
        (r'\bques\s*tion\b', 'question'),
        (r'\bregu\s*la\s*tion\b', 'regulation'),
        (r'\bregula\s*tion\b', 'regulation'),
        (r'\bdocu\s*ment\b', 'document'),
        (r'\bstate\s*ment\b', 'statement'),
        (r'\binvest\s*ment\b', 'investment'),
        (r'\bequip\s*ment\b', 'equipment'),
        (r'\brequire\s*ment\b', 'requirement'),
        (r'\bachieve\s*ment\b', 'achievement'),
        (r'\badvan\s*tage\b', 'advantage'),
        (r'\bknowl\s*edge\b', 'knowledge'),
        (r'\bstra\s*tegy\b', 'strategy'),
        (r'\bstrateg\s*y\b', 'strategy'),
        (r'\bactiv\s*ity\b', 'activity'),
        (r'\bopportun\s*ity\b', 'opportunity'),
        (r'\brespons\s*ibility\b', 'responsibility'),
        (r'\bresponsi\s*bility\b', 'responsibility'),
        (r'\babil\s*ity\b', 'ability'),
        (r'\bqual\s*ity\b', 'quality'),
        (r'\bquant\s*ity\b', 'quantity'),
        (r'\butil\s*ity\b', 'utility'),
        (r'\bsecur\s*ity\b', 'security'),
        (r'\bauthor\s*ity\b', 'authority'),
        (r'\bprior\s*ity\b', 'priority'),
        (r'\bcomplex\s*ity\b', 'complexity'),
        
        # === MORE BUSINESS TERMS ===
        (r'\bemploy\s*er\b', 'employer'),
        (r'\bemploy\s*ment\b', 'employment'),
        (r'\bsales\s*person\b', 'salesperson'),
        (r'\bread\s*ing\b', 'reading'),
        (r'\bwrit\s*ing\b', 'writing'),
        (r'\bspeak\s*ing\b', 'speaking'),
        (r'\blisten\s*ing\b', 'listening'),
        (r'\blearn\s*ing\b', 'learning'),
        (r'\btrain\s*ing\b', 'training'),
        (r'\bplan\s*ning\b', 'planning'),
        (r'\bbudget\s*ing\b', 'budgeting'),
        (r'\baccount\s*ing\b', 'accounting'),
        (r'\bbank\s*ing\b', 'banking'),
        (r'\bpric\s*ing\b', 'pricing'),
        (r'\bbrand\s*ing\b', 'branding'),
        (r'\bsell\s*ing\b', 'selling'),
        (r'\bbuy\s*ing\b', 'buying'),
        (r'\bship\s*ping\b', 'shipping'),
        (r'\bpack\s*aging\b', 'packaging'),
        (r'\bpromot\s*ion\b', 'promotion'),
        (r'\bpromo\s*tion\b', 'promotion'),
        (r'\bdistri\s*bution\b', 'distribution'),
        (r'\bproduct\s*ion\b', 'production'),
        (r'\bcompet\s*ition\b', 'competition'),
        (r'\bcompeti\s*tion\b', 'competition'),
        (r'\bposi\s*tion\b', 'position'),
        (r'\bcondi\s*tion\b', 'condition'),
        (r'\btransi\s*tion\b', 'transition'),
        (r'\bsolu\s*tion\b', 'solution'),
        (r'\beval\s*uation\b', 'evaluation'),
        (r'\bsitu\s*ation\b', 'situation'),
        (r'\bpresen\s*tation\b', 'presentation'),
        (r'\bappli\s*cation\b', 'application'),
        (r'\binforma\s*tion\b', 'information'),
        (r'\bimportant\b', 'important'),
        (r'\bimport\s*ant\b', 'important'),
        (r'\bdifferent\b', 'different'),
        (r'\bdiffer\s*ent\b', 'different'),
        (r'\beffect\s*ive\b', 'effective'),
        (r'\bproduct\s*ive\b', 'productive'),
        (r'\bposit\s*ive\b', 'positive'),
        (r'\bnegat\s*ive\b', 'negative'),
        (r'\bcreate\s*ive\b', 'creative'),
        (r'\bcompet\s*itive\b', 'competitive'),
        
        # === ADDITIONAL COMMON WORDS ===
        (r'\bfollow\s*ing\b', 'following'),
        (r'\binclu\s*ding\b', 'including'),
        (r'\bbecome\s*ing\b', 'becoming'),
        (r'\bbehav\s*ior\b', 'behavior'),
        (r'\binter\s*est\b', 'interest'),
        (r'\binter\s*net\b', 'internet'),
        (r'\binter\s*view\b', 'interview'),
        (r'\binter\s*nal\b', 'internal'),
        (r'\binter\s*action\b', 'interaction'),
        (r'\bextern\s*al\b', 'external'),
        (r'\borigin\s*al\b', 'original'),
        (r'\bperson\s*al\b', 'personal'),
        (r'\bproces\s*s\b', 'process'),
        (r'\bprogr\s*am\b', 'program'),
        (r'\bprob\s*lem\b', 'problem'),
        (r'\bpur\s*pose\b', 'purpose'),
        (r'\bpur\s*chase\b', 'purchase'),
        (r'\bstand\s*ard\b', 'standard'),
        (r'\bpart\s*ner\b', 'partner'),
        (r'\bpart\s*nership\b', 'partnership'),
        (r'\bleader\s*ship\b', 'leadership'),
        (r'\bmember\s*ship\b', 'membership'),
        (r'\bowner\s*ship\b', 'ownership'),
        (r'\bspons\s*orship\b', 'sponsorship'),
        (r'\bintern\s*ship\b', 'internship'),
        (r'\bscholar\s*ship\b', 'scholarship'),
        (r'\bcitizen\s*ship\b', 'citizenship'),
        (r'\bfriend\s*ship\b', 'friendship'),
        (r'\bwork\s*place\b', 'workplace'),
        (r'\bmarket\s*place\b', 'marketplace'),
        
        # === FIX COMMON SHORT SPLITS ===
        (r'\bwi\s*th\b', 'with'),
        (r'\bwit\s*h\b', 'with'),
        (r'\bth\s*at\b', 'that'),
        (r'\btha\s*t\b', 'that'),
        (r'\bth\s*is\b', 'this'),
        (r'\bthi\s*s\b', 'this'),
        (r'\bth\s*ey\b', 'they'),
        (r'\bthe\s*y\b', 'they'),
        (r'\bth\s*em\b', 'them'),
        (r'\bthe\s*m\b', 'them'),
        (r'\bth\s*eir\b', 'their'),
        (r'\bthei\s*r\b', 'their'),
        (r'\bth\s*ere\b', 'there'),
        (r'\bther\s*e\b', 'there'),
        (r'\bth\s*ese\b', 'these'),
        (r'\bthes\s*e\b', 'these'),
        (r'\bwh\s*ich\b', 'which'),
        (r'\bwhic\s*h\b', 'which'),
        (r'\bwh\s*en\b', 'when'),
        (r'\bwhe\s*n\b', 'when'),
        (r'\bwh\s*ere\b', 'where'),
        (r'\bwher\s*e\b', 'where'),
        (r'\bwh\s*at\b', 'what'),
        (r'\bwha\s*t\b', 'what'),
        (r'\bab\s*out\b', 'about'),
        (r'\babou\s*t\b', 'about'),
        (r'\bfr\s*om\b', 'from'),
        (r'\bfro\s*m\b', 'from'),
        (r'\bhave\b', 'have'),
        (r'\bha\s*ve\b', 'have'),
        (r'\bsh\s*ould\b', 'should'),
        (r'\bshou\s*ld\b', 'should'),
        (r'\bwo\s*uld\b', 'would'),
        (r'\bwoul\s*d\b', 'would'),
        (r'\bco\s*uld\b', 'could'),
        (r'\bcoul\s*d\b', 'could'),
        (r'\bbe\s*cause\b', 'because'),
        (r'\bbecau\s*se\b', 'because'),
        (r'\bbefor\s*e\b', 'before'),
        (r'\baft\s*er\b', 'after'),
        (r'\bafte\s*r\b', 'after'),
        (r'\both\s*er\b', 'other'),
        (r'\bothe\s*r\b', 'other'),
        (r'\beff\s*ect\b', 'effect'),
        (r'\beffec\s*t\b', 'effect'),
    ]
    
    for pattern, replacement in common_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Preserve case for capitalized versions
        if replacement[0].isupper():
            text = re.sub(pattern, replacement, text)
    
    # =========================================================================
    # 2. FIX HYPHENATION ISSUES (11k+ fixes)
    # =========================================================================
    # Fix "word -word" → "word-word"
    text = re.sub(r'(\w)\s+-(\w)', r'\1-\2', text)
    # Fix "word- word" → "word-word"  
    text = re.sub(r'(\w)-\s+(\w)', r'\1-\2', text)
    # Fix "word - word" → "word-word"
    text = re.sub(r'(\w)\s+-\s+(\w)', r'\1-\2', text)
    
    # =========================================================================
    # 3. FIX PUNCTUATION SPACING (1.3k+ fixes)
    # =========================================================================
    # Remove space before punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    # Ensure space after punctuation (but not in URLs or numbers)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    
    # =========================================================================
    # 4. FIX DOUBLE/MULTIPLE SPACES
    # =========================================================================
    text = re.sub(r'\s{2,}', ' ', text)
    
    # =========================================================================
    # 4.5. FIX POSSESSIVE/CONTRACTION MISSING SPACES (5k+ issues)
    # =========================================================================
    # Fix patterns like "business'slegal" → "business's legal"
    # Fix patterns like "isn'tshe" → "isn't she"
    # Fix patterns like "don'tget" → "don't get"
    
    # Possessive 's followed by lowercase letter (need space)
    text = re.sub(r"(\w+)'s([a-z])", r"\1's \2", text)
    
    # Contraction 't followed by lowercase letter (need space) - e.g., isn't, don't, won't
    text = re.sub(r"(\w+)'t([a-z])", r"\1't \2", text)
    
    # Contraction 've followed by lowercase letter (need space) - e.g., would've
    text = re.sub(r"(\w+)'ve([a-z])", r"\1've \2", text)
    
    # Contraction 're followed by lowercase letter (need space) - e.g., they're
    text = re.sub(r"(\w+)'re([a-z])", r"\1're \2", text)
    
    # Contraction 'll followed by lowercase letter (need space) - e.g., they'll
    text = re.sub(r"(\w+)'ll([a-z])", r"\1'll \2", text)
    
    # Contraction 'd followed by lowercase letter (need space) - e.g., they'd
    text = re.sub(r"(\w+)'d([a-z])", r"\1'd \2", text)
    
    # =========================================================================
    # 4.6. FIX ADDITIONAL BROKEN WORDS (found in analysis)
    # =========================================================================
    additional_fixes = [
        # Words found in spacing analysis that were still broken
        (r'\bciv\s*il\b', 'civil'),
        (r'\bmaj\s*ority\b', 'majority'),
        (r'\bret\s*ailers\b', 'retailers'),
        (r'\brath\s*er\b', 'rather'),
        (r'\bcons\s*umers\b', 'consumers'),
        (r'\bcontroll\s*ing\b', 'controlling'),
        (r'\bslott\s*ing\b', 'slotting'),
        (r'\bsimplifyi\s*ng\b', 'simplifying'),
        (r'\beffecti\s*vely\b', 'effectively'),
        (r'\blisteni\s*ng\b', 'listening'),
        (r'\bmaki\s*ng\b', 'making'),
        (r'\btaki\s*ng\b', 'taking'),
        (r'\bhavi\s*ng\b', 'having'),
        (r'\bgivi\s*ng\b', 'giving'),
        (r'\busi\s*ng\b', 'using'),
        (r'\bmeani\s*ng\b', 'meaning'),
        (r'\bbec\s*ause\b', 'because'),
        (r'\bmes\s*sage\b', 'message'),
        (r'\baff\s*ect\b', 'affect'),
        (r'\bspe\s*cific\b', 'specific'),
        (r'\bdiffi\s*cult\b', 'difficult'),
        (r'\bsemi\s*nar\b', 'seminar'),
        (r'\binformati\s*on\b', 'information'),
        (r'\brel\s*y\b', 'rely'),
        (r'\bYo\s*ucan\b', 'You can'),
        (r'\bwit\s*htheir\b', 'with their'),
        (r'\bwit\s*hout\b', 'without'),
        (r'\bwhi\s*ch\b', 'which'),
        (r'\bmone\s*y\b', 'money'),
        (r'\bsho\s*uld\b', 'should'),
        (r'\bcou\s*ld\b', 'could'),
        (r'\bwou\s*ld\b', 'would'),
        (r'\ba\s+re\s+based\b', 'are based'),
        (r'\bsteppings\s*tones\b', 'steppingstones'),
        (r'\btriggerne\s*w\b', 'trigger new'),
        (r'\bveryoutlandish\b', 'very outlandish'),
        (r'\blisteni\s*ngand\b', 'listening and'),
        (r'\bwhi\s*chmay\b', 'which may'),
        (r'\bsimplifyi\s*ngexisting\b', 'simplifying existing'),
        (r'\brath\s*erthan\b', 'rather than'),
        (r'\bciv\s*illitigation\b', 'civil litigation'),
        # More -ing splits
        (r'\bkee\s*ping\b', 'keeping'),
        (r'\bsel\s*ling\b', 'selling'),
        (r'\btel\s*ling\b', 'telling'),
        (r'\bgett\s*ing\b', 'getting'),
        (r'\bsett\s*ing\b', 'setting'),
        (r'\blett\s*ing\b', 'letting'),
        (r'\bputt\s*ing\b', 'putting'),
        (r'\bcutt\s*ing\b', 'cutting'),
        (r'\bhitt\s*ing\b', 'hitting'),
        (r'\bsitt\s*ing\b', 'sitting'),
        # More common splits
        (r'\binfor\s*mation\b', 'information'),
        (r'\beffici\s*ent\b', 'efficient'),
        (r'\beffici\s*ency\b', 'efficiency'),
        (r'\bsuffi\s*cient\b', 'sufficient'),
        (r'\bdefici\s*ent\b', 'deficient'),
        
        # === NEW: -ity word splits (from analysis) ===
        (r'\bprofitabilit\s*y\b', 'profitability'),
        (r'\babilit\s*y\b', 'ability'),
        (r'\bqualit\s*y\b', 'quality'),
        (r'\bliabilit\s*y\b', 'liability'),
        (r'\bfacilit\s*y\b', 'facility'),
        (r'\bflexibilit\s*y\b', 'flexibility'),
        (r'\bresponsibilit\s*y\b', 'responsibility'),
        (r'\bquantit\s*y\b', 'quantity'),
        (r'\bactivit\s*y\b', 'activity'),
        (r'\brealit\s*y\b', 'reality'),
        (r'\bvariet\s*y\b', 'variety'),
        (r'\bcurrenc\s*y\b', 'currency'),
        (r'\bpolic\s*y\b', 'policy'),
        (r'\bphilosoph\s*y\b', 'philosophy'),
        (r'\bentiret\s*y\b', 'entirety'),
        (r'\bhonest\s*y\b', 'honesty'),
        (r'\bwarrant\s*y\b', 'warranty'),
        
        # === NEW: -ly word splits (from analysis) ===
        (r'\bquickl\s*y\b', 'quickly'),
        (r'\blikel\s*y\b', 'likely'),
        (r'\bpositivel\s*y\b', 'positively'),
        (r'\binitiall\s*y\b', 'initially'),
        (r'\bstrictl\s*y\b', 'strictly'),
        (r'\bsimilarl\s*y\b', 'similarly'),
        (r'\bfriendl\s*y\b', 'friendly'),
        (r'\bnecessar\s*y\b', 'necessary'),
        (r'\bhorsepla\s*y\b', 'horseplay'),
        (r'\bhapp\s*y\b', 'happy'),
        (r'\bjul\s*y\b', 'july'),
        (r'\bvar\s*y\b', 'vary'),
        
        # === NEW: -ic word splits (from analysis) ===
        (r'\bstrategi\s*c\b', 'strategic'),
        (r'\bspecifi\s*c\b', 'specific'),
        (r'\bethi\s*c\b', 'ethic'),
        
        # === NEW: -ew/-ow/-elf word splits ===
        (r'\bvie\s*w\b', 'view'),
        (r'\bfollo\s*w\b', 'follow'),
        (r'\bhersel\s*f\b', 'herself'),
        (r'\byoursel\s*f\b', 'yourself'),
        
        # === NEW: Compound word fixes ===
        (r'\brightha\s*nd\b', 'righthand'),
        (r'\bcleanai\s*r\b', 'clean air'),
        (r'\banden\s*d\b', 'and end'),
        (r'\bandh\s*e\b', 'and he'),
        (r'\bthewa\s*y\b', 'the way'),
        (r'\bhisbo\s*ss\b', 'his boss'),
        (r'\bnationalla\s*w\b', 'national law'),
        (r'\bpowerfulwa\s*y\b', 'powerful way'),
        (r'\binformationma\s*y\b', 'information may'),
        (r'\bhelpyo\s*u\b', 'help you'),
        (r'\buseshi\s*gh\b', 'uses high'),
        (r'\briverlogi\s*c\b', 'riverlogic'),
        
        # === NEW: More -ity splits found in analysis ===
        (r'\btangibil\s*ity\b', 'tangibility'),
        (r'\bintegr\s*ity\b', 'integrity'),
        (r'\bliabil\s*ity\b', 'liability'),
        (r'\bcommun\s*ity\b', 'community'),
        (r'\bhospital\s*ity\b', 'hospitality'),
        (r'\bfacil\s*ity\b', 'facility'),
        (r'\bequ\s*ity\b', 'equity'),
        (r'\bviabil\s*ity\b', 'viability'),
        (r'\bresponsibil\s*ity\b', 'responsibility'),
        (r'\bcapabil\s*ity\b', 'capability'),
        (r'\bpossibil\s*ity\b', 'possibility'),
        (r'\bstabil\s*ity\b', 'stability'),
        (r'\bvisibil\s*ity\b', 'visibility'),
        (r'\bflexibil\s*ity\b', 'flexibility'),
        (r'\bcredibil\s*ity\b', 'credibility'),
        (r'\bdurabil\s*ity\b', 'durability'),
        (r'\bavailabil\s*ity\b', 'availability'),
        (r'\baccountabil\s*ity\b', 'accountability'),
        (r'\breliabil\s*ity\b', 'reliability'),
        (r'\bsustainabil\s*ity\b', 'sustainability'),
        
        # === NEW: Run-on word fixes ===
        (r'\byo\s*ucan\b', 'you can'),
        (r'\by\s*ouachieve\b', 'you achieve'),
        (r'\by\s*ouhave\b', 'you have'),
        (r'\by\s*oushould\b', 'you should'),
        (r'\by\s*ounext\b', 'you next'),
        (r'\byo\s*uare\b', 'you are'),
        (r'\bt\s*ocalculate\b', 'to calculate'),
        (r'\bt\s*oinfluence\b', 'to influence'),
        (r'\bt\s*ocheck\b', 'to check'),
        (r'\bo\s*wnstore\b', 'own store'),
        (r'\bo\s*wnideas\b', 'own ideas'),
        (r'\bo\s*raffect\b', 'or affect'),
        (r'\bo\s*fcompetitors\b', 'of competitors'),
        (r'\bo\s*ffinancial\b', 'of financial'),
        (r'\bo\s*fnegotiating\b', 'of negotiating'),
        (r'\bo\s*nanyone\b', 'on anyone'),
        (r'\bb\s*eexperts\b', 'be experts'),
        (r'\bb\s*ylogical\b', 'by logical'),
        (r'\bb\s*ycombining\b', 'by combining'),
        (r'\bb\s*utdaily\b', 'but daily'),
        (r'\bb\s*yfollowing\b', 'by following'),
        (r'\bb\s*eviewed\b', 'be viewed'),
        (r'\bb\s*ymultiplying\b', 'by multiplying'),
        (r'\bs\s*etassumptions\b', 'set assumptions'),
        (r'\bs\s*othey\b', 'so they'),
        (r'\bf\s*argreater\b', 'far greater'),
        (r'\bf\s*ewquestions\b', 'few questions'),
        (r'\bho\s*wclosely\b', 'how closely'),
        (r'\bw\s*eall\b', 'we all'),
        (r'\bj\s*obapplicant\b', 'job applicant'),
        (r'\bx\s*yzgrocery\b', 'xyz grocery'),
        (r'\bda\s*ysago\b', 'days ago'),
        (r'\bd\s*aycare\b', 'daycare'),
        (r'\ban\s*y\b', 'any'),
        (r'\bcantr\s*y\b', 'can try'),
        (r'\bsinc\s*ey\b', 'since y'),
        (r'\bcall\s*y\b', 'cally'),  # Likely a name
    ]
    
    for pattern, replacement in additional_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # =========================================================================
    # 5. GENERAL SPLIT WORD FIX (remaining cases)
    # =========================================================================
    # Valid small words that should NOT be merged
    valid_short = {
        'a', 'i', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 
        'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 
        'us', 'we', 'a.', 'b.', 'c.', 'd.', 'e.', 're', 'vs', 'ok', 'ex'
    }
    
    def merge_prefix_careful(match):
        p, w = match.group(1), match.group(2)
        if p.lower() in valid_short: 
            return match.group(0)
        return p + w

    # Merge isolated 1-2 chars followed by 3+ chars (e.g., "th eir" → "their")
    # Added (?<!') to prevent merging possessives like "owner's invention" -> "owner'sinvention"
    text = re.sub(r"(?<!')\b([a-zA-Z]{1,2})\s+([a-zA-Z]{3,})\b", merge_prefix_careful, text)
    
    def merge_suffix_careful(match):
        w, s = match.group(1), match.group(2)
        if s.lower() in valid_short: 
            return match.group(0)
        # Don't merge with answer options A-E
        if s in {'A','B','C','D','E'}: 
            return match.group(0)
        # For single char suffixes, only merge common word endings
        if len(s) == 1:
            if s.lower() not in {'s', 'd', 'r', 'n', 't', 'l', 'e', 'h', 'k', 'p', 'g', 'm'}: 
                return match.group(0)
        return w + s

    # Merge 2+ chars followed by isolated 1-2 chars (e.g., "wit h" → "with")
    text = re.sub(r'\b([a-zA-Z]{2,})\s+([a-zA-Z]{1,2})\b', merge_suffix_careful, text)
    
    # =========================================================================
    # 6. FINAL CLEANUP
    # =========================================================================
    # One more pass for double spaces that may have been created
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()


def _parse_answer_key(lines: List[str]) -> Dict[int, Dict[str, str]]:
    start_idx = -1
    
    # Try explicit headers first
    for i in range(len(lines) - 1, -1, -1):
        if re.search(r"answer\s*(key|section)", lines[i], re.IGNORECASE):
            start_idx = i
            break
            
    if start_idx == -1:
         for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().upper() == "KEY":
                start_idx = i
                break

    # If no header, use sequence detection (robust)
    if start_idx == -1:
        # Scan from 10% to find "1. X" followed by "2. Y"
        search_start = int(len(lines) * 0.1)
        pat_num = re.compile(r"^\s*(\d{1,3})\s*[:.-]?\s*([A-E])\b", re.IGNORECASE)
        
        for i in range(search_start, len(lines)):
            m = pat_num.match(lines[i])
            if m and int(m.group(1)) == 1:
                # Potential start, verify sequence
                # Look for 2, 3 in next 50 lines
                found_next = False
                cur_next = 2
                look_ahead_range = 50
                for j in range(i + 1, min(i + look_ahead_range * cur_next, len(lines))):
                     m2 = pat_num.match(lines[j])
                     if m2:
                         num_found = int(m2.group(1))
                         if num_found == cur_next:
                             cur_next += 1
                             if cur_next > 3: # Found 1, 2, 3 - confident
                                 found_next = True
                                 break
                
                if found_next:
                    start_idx = i
                    break

    # Last resort fallback
    if start_idx == -1:
        start_idx = max(0, int(len(lines) * 0.8))

    answers = {}
    # Strict pattern for answer key line: Number + Sep + Letter + Explanation
    pattern = re.compile(r"^\s*(\d{1,3})\s*[:.-]?\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    
    i = start_idx
    while i < len(lines):
        line = lines[i]
        # skip header lines in the key section
        if _looks_like_header_line(line) or "answer key" in line.lower():
            i += 1
            continue
            
        match = pattern.search(line)
        if match:
            num = int(match.group(1))
            let = match.group(2).upper()
            expl = match.group(3).strip()
            
            # Simple multiline capture for explanation
            i += 1
            while i < len(lines):
                next_line = lines[i]
                # Stop if next line looks like new answer or header
                if pattern.search(next_line) or _looks_like_header_line(next_line):
                    break
                expl += " " + _fix_broken_words(next_line.strip())
                i += 1
                
            if 1 <= num <= 100:
                answers[num] = {"letter": let, "explanation": _fix_broken_words(expl)}
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
            # First normalize standard whitespace
            prompt = _normalize_whitespace(current_q["prompt"])
            # Then fix broken word splits
            current_q["prompt"] = _fix_broken_words(prompt)
            
            for opt in current_q["options"]:
                text = _normalize_whitespace(opt["text"])
                opt["text"] = _fix_broken_words(text)
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

def _sanitize_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized = []
    for q in questions:
        q_copy = dict(q)
        for key in ("correct_index", "correct_letter", "explanation"):
            q_copy.pop(key, None)
        sanitized.append(q_copy)
    return sanitized

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

def _get_all_tests_for_session(force_refresh=False) -> Dict[str, Any]:
    all_tests = {}
    
    global _STATIC_TESTS_CACHE
    if force_refresh:
        _STATIC_TESTS_CACHE.clear()

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
    sid = _get_session_id()
    _load_session_data(sid)
    return render_template("index.html", default_random_order=DEFAULT_RANDOM_ORDER)

@app.route("/settings")
def settings():
    return redirect(f"{url_for('home')}#/settings", code=302)

@app.route("/api/tests")
def list_tests():
    force = request.args.get("reload") == "1"
    data = _get_all_tests_for_session(force_refresh=force)
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
    
    sanitized_questions = _sanitize_questions(qs)
        
    return jsonify({
        "test": {"id": test["id"], "name": test["name"], "total": len(test["questions"])},
        "questions": sanitized_questions,
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
        

    sanitized_questions = _sanitize_questions(questions)

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
        "description": parsed.get("description", ""),
        "questions": parsed["questions"],
        "question_count": len(parsed["questions"]),
        "test": {"id": uid, "name": parsed["name"], "total": len(parsed["questions"])}
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

@app.route("/api/tests/<test_id>/results", methods=["POST"])
def store_results(test_id):
    sid = _get_session_id()
    payload = request.get_json(silent=True) or {}
    results = payload.get("results", [])
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
