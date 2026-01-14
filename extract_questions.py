import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

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

def _extract_clean_lines(source: Path) -> List[str]:
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

def _normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    
    # Fix specific common broken words
    text = text.replace("SOURC E", "SOURCE")
    text = re.sub(r"\b(SOURC)\s+(E)\b", "SOURCE", text)
    
    text = re.sub(r"\b(\w+)\s+(ment|tion|ing|able|ible|ness)\b", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()

def _fix_broken_words(text: str) -> str:
    if not text: return ""
    
    # =========================================================================
    # 1. FIX COMMON SPLIT WORDS (highest impact)
    # =========================================================================
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
    
    # =========================================================================
    # 2. FIX HYPHENATION ISSUES
    # =========================================================================
    text = re.sub(r'(\w)\s+-(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)-\s+(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)\s+-\s+(\w)', r'\1-\2', text)
    
    # =========================================================================
    # 3. FIX PUNCTUATION SPACING
    # =========================================================================
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    
    # =========================================================================
    # 4. FIX DOUBLE/MULTIPLE SPACES
    # =========================================================================
    text = re.sub(r'\s{2,}', ' ', text)
    
    # =========================================================================
    # 4.5. FIX POSSESSIVE/CONTRACTION MISSING SPACES
    # =========================================================================
    text = re.sub(r"(\w+)'s([a-z])", r"\1's \2", text)
    text = re.sub(r"(\w+)'t([a-z])", r"\1't \2", text)
    text = re.sub(r"(\w+)'ve([a-z])", r"\1've \2", text)
    text = re.sub(r"(\w+)'re([a-z])", r"\1're \2", text)
    text = re.sub(r"(\w+)'ll([a-z])", r"\1'll \2", text)
    text = re.sub(r"(\w+)'d([a-z])", r"\1'd \2", text)
    
    # =========================================================================
    # 4.6. FIX ADDITIONAL BROKEN WORDS (found in analysis)
    # =========================================================================
    additional_fixes = [
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
        (r'\binfor\s*mation\b', 'information'),
        (r'\beffici\s*ent\b', 'efficient'),
        (r'\beffici\s*ency\b', 'efficiency'),
        (r'\bsuffi\s*cient\b', 'sufficient'),
        (r'\bdefici\s*ent\b', 'deficient'),
    ]
    
    for pattern, replacement in additional_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # =========================================================================
    # 5. GENERAL SPLIT WORD FIX (remaining cases)
    # =========================================================================
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

    # Added (?<!') to prevent merging possessives like "owner's invention" -> "owner'sinvention"
    text = re.sub(r"(?<!')\b([a-zA-Z]{1,2})\s+([a-zA-Z]{3,})\b", merge_prefix_careful, text)
    
    def merge_suffix_careful(match):
        w, s = match.group(1), match.group(2)
        if s.lower() in valid_short: 
            return match.group(0)
        if s in {'A','B','C','D','E'}: 
            return match.group(0)
        if len(s) == 1:
            if s.lower() not in {'s', 'd', 'r', 'n', 't', 'l', 'e', 'h', 'k', 'p', 'g', 'm'}: 
                return match.group(0)
        return w + s

    text = re.sub(r'\b([a-zA-Z]{2,})\s+([a-zA-Z]{1,2})\b', merge_suffix_careful, text)
    
    # Final cleanup
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()

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
        search_start = int(len(lines) * 0.1)
        pat_num = re.compile(r"^\s*(\d{1,3})\s*[:.-]\s*[A-E]\b", re.IGNORECASE)
        
        for i in range(search_start, len(lines)):
            m = pat_num.match(lines[i])
            if m and int(m.group(1)) == 1:
                found_next = False
                cur_next = 2
                look_ahead_range = 50
                for j in range(i + 1, min(i + look_ahead_range * cur_next, len(lines))):
                     m2 = pat_num.match(lines[j])
                     if m2:
                          num_found = int(m2.group(1))
                          if num_found == cur_next:
                              cur_next += 1
                              if cur_next > 3: 
                                  found_next = True
                                  break
                
                if found_next:
                    start_idx = i
                    break

        if start_idx == -1:
            pat_num_2 = re.compile(r"^\s*2\s*[:.-]\s*[A-E]\b", re.IGNORECASE)
            for i in range(search_start, len(lines)):
                m = pat_num_2.match(lines[i])
                if m:
                    found_next = False
                    cur_next = 3
                    look_ahead_range = 250
                    for j in range(i + 1, min(i + look_ahead_range * (cur_next-1), len(lines))):
                         m2 = pat_num.match(lines[j]) 
                         if m2:
                             num_found = int(m2.group(1))
                             if num_found == cur_next:
                                 found_next = True
                                 break
                    if found_next:
                        start_idx = i
                        break

    if start_idx == -1:
        start_idx = max(0, int(len(lines) * 0.2))

    answers = {}
    pattern = re.compile(r"(?<!\d)(\d{1,3})\s*[:.\-)]\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if _looks_like_header_line(line) or "answer key" in line.lower():
            i += 1
            continue
            
        match = pattern.search(line)
        if match:
            num = int(match.group(1))
            let = match.group(2).upper()
            expl = match.group(3).strip()
            
            i += 1
            while i < len(lines):
                next_line = lines[i]
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
            prompt = _normalize_whitespace(current_q["prompt"])
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
        
        final_questions.append({
            "number": num,
            "question": q["prompt"],
            "options": [o["text"] for o in q["options"]],
            "correct_letter": ans_letter if ans_letter else "?",
            "explanation": explanation if explanation else "No explanation available"
        })
        seen_ids.add(num)
        
    return final_questions

def main():
    base_dir = Path("tests")
    if not base_dir.exists():
        print("No 'tests' dir found.")
        return

    all_pdfs = list(base_dir.glob("*.pdf"))
    all_pdfs.sort(key=lambda x: x.name)
    
    print(f"Found {len(all_pdfs)} PDF files.")
    
    with open("all_questions.txt", "w", encoding="utf-8") as f_out:
        for i, pdf_path in enumerate(all_pdfs):
            print(f"Processing {pdf_path.name}...")
            try:
                lines = _extract_clean_lines(pdf_path)
                answers = _parse_answer_key(lines)
                questions = _smart_parse_questions(lines, answers)
                
                f_out.write(f"\n--- FILE: {pdf_path.name} ---\n")
                if not questions:
                    f_out.write("NO QUESTIONS FOUND\n")
                    continue
                    
                for q in questions:
                    f_out.write(f"{q['number']}. {q['question']}\n")
                    for opt in q['options']:
                        f_out.write(f"  {opt}\n")
                    f_out.write(f"  * {q['correct_letter']}\n")
                    f_out.write(f"Explanation: {q['explanation']}\n\n")
                    
            except Exception as e:
                print(f"Error processing {pdf_path.name}: {e}")
                
    print("Done! All questions saved to all_questions.txt")

if __name__ == "__main__":
    main()
