#!/usr/bin/env python3
"""
Compare GitHub parser vs Local parser on tests 1-71.
Checks for spacing errors, missing questions, missing options, and explanation issues.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader

# =============================================================================
# GITHUB PARSER (simpler, original version from repository)
# =============================================================================

def github_looks_like_header(text: str) -> bool:
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

def github_normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = text.replace("SOURC E", "SOURCE")
    text = re.sub(r"\b(SOURC)\s+(E)\b", "SOURCE", text)
    text = re.sub(r"\b(\w+)\s+(ment|tion|ing|able|ible|ness)\b", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()

def github_extract_clean_lines(source: Path) -> List[str]:
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
                
                if "specialist levels." in line:
                    line = line.replace("specialist levels.", "").strip()
                
                if github_looks_like_header(line):
                    continue
                    
                lines.append(line)
    
    counts = {}
    for l in lines:
        counts[l] = counts.get(l, 0) + 1
    
    threshold = max(2, len(reader.pages) // 2)
    final_lines = [l for l in lines if counts[l] < threshold]
    return final_lines

def github_fix_broken_words(text: str) -> str:
    """GitHub version - fewer fixes"""
    if not text: return ""
    
    common_fixes = [
        (r'\bbusi?\s*ness\b', 'business'),
        (r'\bfi\s*nance\b', 'finance'),
        (r'\bin\s*for\s*ma\s*tion\b', 'information'),
        (r'\bman\s*age\s*ment\b', 'management'),
        (r'\bcus\s*tom\s*er\b', 'customer'),
        (r'\bcom\s*pa\s*ny\b', 'company'),
        (r'\bpro\s*duct\b', 'product'),
        (r'\bser\s*vice\b', 'service'),
        (r'\bmar\s*ket\s*ing\b', 'marketing'),
        (r'\bem\s*ploy\s*ee\b', 'employee'),
        (r'\bor\s*gan\s*iza\s*tion\b', 'organization'),
        (r'\bSOURC\s*E\b', 'SOURCE'),
        (r'\bwi\s*th\b', 'with'),
        (r'\bth\s*at\b', 'that'),
        (r'\bth\s*is\b', 'this'),
    ]
    
    for pattern, replacement in common_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    text = re.sub(r'(\w)\s+-(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)-\s+(\w)', r'\1-\2', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()

def github_parse_answer_key(lines: List[str]) -> Dict[int, Dict[str, str]]:
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
        pat_num = re.compile(r"^\s*(\d{1,3})\s*[:.-]?\s*([A-E])\b", re.IGNORECASE)
        
        for i in range(search_start, len(lines)):
            m = pat_num.match(lines[i])
            if m and int(m.group(1)) == 1:
                found_next = False
                cur_next = 2
                for j in range(i + 1, min(i + 100, len(lines))):
                    m2 = pat_num.match(lines[j])
                    if m2:
                        if int(m2.group(1)) == cur_next:
                            cur_next += 1
                            if cur_next > 3:
                                found_next = True
                                break
                if found_next:
                    start_idx = i
                    break

    if start_idx == -1:
        start_idx = max(0, int(len(lines) * 0.8))

    answers = {}
    pattern = re.compile(r"^\s*(\d{1,3})\s*[:.-]?\s*([A-E])\b\s*(.*)", re.IGNORECASE)
    
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if github_looks_like_header(line):
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
                if pattern.search(next_line) or github_looks_like_header(next_line):
                    break
                expl += " " + next_line.strip()
                i += 1
                
            if 1 <= num <= 100:
                answers[num] = {"letter": let, "explanation": expl}
        else:
            i += 1
            
    return answers

def github_parse_questions(lines: List[str], answers: Dict[int, Any]) -> List[Dict[str, Any]]:
    questions = []
    current_q = None
    
    q_start_re = re.compile(r"^(\d{1,3})\s*[).:\-]\s+(.*)")
    opt_start_re = re.compile(r"^\s*([A-E])\s*[).:\-]\s*(.*)")

    def finalize_current():
        nonlocal current_q
        if current_q:
            current_q["prompt"] = github_fix_broken_words(github_normalize_whitespace(current_q["prompt"]))
            for opt in current_q["options"]:
                opt["text"] = github_fix_broken_words(github_normalize_whitespace(opt["text"]))
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
            current_q = {"number": num, "prompt": q_match.group(2), "options": []}
            continue

        opt_match = opt_start_re.match(line)
        if opt_match:
            label = opt_match.group(1).upper()
            text = opt_match.group(2)
            
            if not current_q:
                continue
            current_q["options"].append({"label": label, "text": text})
            continue

        if current_q:
            if current_q["options"]:
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
        expected = ['A','B','C','D']
        if 'E' in labels:
            expected.append('E')
        
        new_options = []
        for exp_label in expected:
            found = next((o for o in q["options"] if o["label"] == exp_label), None)
            if found:
                new_options.append(found)
            else:
                new_options.append({"label": exp_label, "text": "[Option missing]"})
        q["options"] = new_options
        
        ans_data = answers.get(num)
        
        final_questions.append({
            "number": num,
            "question": q["prompt"],
            "options": [o["text"] for o in q["options"]],
            "correct_letter": ans_data["letter"] if ans_data else "?",
            "explanation": ans_data["explanation"] if ans_data else ""
        })
        seen_ids.add(num)
        
    return final_questions

# =============================================================================
# LOCAL PARSER (from app.py - comprehensive version)
# =============================================================================

# Import local app.py functions
sys.path.insert(0, str(Path(__file__).parent))
from app import (
    _looks_like_header_line as local_looks_like_header,
    _normalize_whitespace as local_normalize_whitespace,
    _extract_clean_lines as local_extract_clean_lines,
    _fix_broken_words as local_fix_broken_words,
    _parse_answer_key as local_parse_answer_key,
    _smart_parse_questions as local_parse_questions
)

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def count_spacing_issues(text: str) -> int:
    """Count REAL spacing issues (excluding valid possessives/contractions/short words)"""
    issues = 0
    
    # Known valid short words
    valid_short = {
        'a', 'i', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 
        'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 
        'us', 'we', 're', 'vs', 'ok', 'ex', 'id', 'tv', 'uk', 'dc', 'pc',
        'am', 'pm', 'ad', 'bc', 'hr', 'mr', 'ms', 'dr', 'st', 'nd', 'rd', 'th'
    }
    
    # Split words (2 chars followed by space then 3+ chars)
    # EXCLUDE: possessive patterns and valid short words
    for m in re.finditer(r'\b([a-zA-Z]{1,2})\s+([a-zA-Z]{3,})\b', text):
        start = m.start()
        prefix = m.group(1).lower()
        # Skip if preceded by apostrophe (possessive/contraction)
        if start > 0 and text[start-1] == "'":
            continue
        # Skip valid short words
        if prefix in valid_short:
            continue
        issues += 1
    
    # Split words (3+ chars followed by space then 1-2 chars)
    for m in re.finditer(r'\b([a-zA-Z]{3,})\s+([a-zA-Z]{1,2})\b', text):
        suffix = m.group(2).lower()
        # Skip valid short words
        if suffix in valid_short:
            continue
        # Skip answer options
        if suffix.upper() in {'A', 'B', 'C', 'D', 'E'}:
            continue
        issues += 1
    
    # Broken hyphenation
    issues += len(re.findall(r'\w\s+-\s*\w|\w\s*-\s+\w', text))
    
    # Space before punctuation
    issues += len(re.findall(r'\s+[.,;:!?]', text))
    
    return issues

def analyze_pdf(pdf_path: Path) -> Dict[str, Any]:
    """Analyze a single PDF with both parsers"""
    result = {
        "file": pdf_path.name,
        "github": {"questions": 0, "missing_options": 0, "spacing_issues": 0, "empty_explanations": 0},
        "local": {"questions": 0, "missing_options": 0, "spacing_issues": 0, "empty_explanations": 0}
    }
    
    try:
        # GitHub parser
        gh_lines = github_extract_clean_lines(pdf_path)
        gh_answers = github_parse_answer_key(gh_lines)
        gh_questions = github_parse_questions(gh_lines, gh_answers)
        
        result["github"]["questions"] = len(gh_questions)
        for q in gh_questions:
            # Count missing options
            for opt in q["options"]:
                if "[Option missing]" in opt or not opt.strip():
                    result["github"]["missing_options"] += 1
            # Count spacing issues
            result["github"]["spacing_issues"] += count_spacing_issues(q["question"])
            for opt in q["options"]:
                result["github"]["spacing_issues"] += count_spacing_issues(opt)
            result["github"]["spacing_issues"] += count_spacing_issues(q["explanation"])
            # Empty explanations
            if not q["explanation"].strip() or q["explanation"] == "No explanation available":
                result["github"]["empty_explanations"] += 1
                
    except Exception as e:
        result["github"]["error"] = str(e)
    
    try:
        # Local parser
        local_lines = local_extract_clean_lines(pdf_path)
        local_answers = local_parse_answer_key(local_lines)
        local_questions = local_parse_questions(local_lines, local_answers)
        
        result["local"]["questions"] = len(local_questions)
        for q in local_questions:
            # Count missing options
            for opt in q["options"]:
                if "[Option missing]" in opt or not opt.strip():
                    result["local"]["missing_options"] += 1
            # Count spacing issues
            result["local"]["spacing_issues"] += count_spacing_issues(q["question"])
            for opt in q["options"]:
                result["local"]["spacing_issues"] += count_spacing_issues(opt)
            result["local"]["spacing_issues"] += count_spacing_issues(q["explanation"])
            # Empty explanations
            if not q["explanation"].strip() or q["explanation"] == "No explanation available":
                result["local"]["empty_explanations"] += 1
                
    except Exception as e:
        result["local"]["error"] = str(e)
    
    return result

def main():
    tests_dir = Path("tests")
    if not tests_dir.exists():
        print("Error: tests directory not found")
        return
    
    pdfs = sorted(tests_dir.glob("*.pdf"), key=lambda x: int(x.stem) if x.stem.isdigit() else 999)
    
    print(f"Analyzing {len(pdfs)} PDFs with both parsers...\n")
    
    totals = {
        "github": {"questions": 0, "missing_options": 0, "spacing_issues": 0, "empty_explanations": 0},
        "local": {"questions": 0, "missing_options": 0, "spacing_issues": 0, "empty_explanations": 0}
    }
    
    results = []
    
    for pdf in pdfs:
        result = analyze_pdf(pdf)
        results.append(result)
        
        for parser in ["github", "local"]:
            if "error" not in result[parser]:
                for key in totals[parser]:
                    totals[parser][key] += result[parser][key]
    
    # Print summary
    print("=" * 70)
    print("PARSER COMPARISON SUMMARY (Tests 1-71)")
    print("=" * 70)
    print(f"\n{'Metric':<30} {'GitHub Parser':<20} {'Local Parser':<20}")
    print("-" * 70)
    print(f"{'Total Questions':<30} {totals['github']['questions']:<20} {totals['local']['questions']:<20}")
    print(f"{'Missing Options':<30} {totals['github']['missing_options']:<20} {totals['local']['missing_options']:<20}")
    print(f"{'Spacing Issues':<30} {totals['github']['spacing_issues']:<20} {totals['local']['spacing_issues']:<20}")
    print(f"{'Empty Explanations':<30} {totals['github']['empty_explanations']:<20} {totals['local']['empty_explanations']:<20}")
    
    # Calculate improvements
    print("\n" + "=" * 70)
    print("IMPROVEMENT (Local vs GitHub)")
    print("=" * 70)
    
    for metric in ["missing_options", "spacing_issues", "empty_explanations"]:
        gh_val = totals["github"][metric]
        local_val = totals["local"][metric]
        diff = gh_val - local_val
        if gh_val > 0:
            pct = (diff / gh_val) * 100
            print(f"{metric.replace('_', ' ').title():<30} {diff:+d} ({pct:+.1f}%)")
        else:
            print(f"{metric.replace('_', ' ').title():<30} {diff:+d}")
    
    # Show PDFs with differences
    print("\n" + "=" * 70)
    print("PDFs WITH NOTABLE DIFFERENCES")
    print("=" * 70)
    
    for r in results:
        gh = r["github"]
        loc = r["local"]
        
        if "error" in gh or "error" in loc:
            print(f"\n{r['file']}: ERROR")
            continue
            
        spacing_diff = gh["spacing_issues"] - loc["spacing_issues"]
        missing_diff = gh["missing_options"] - loc["missing_options"]
        
        if abs(spacing_diff) >= 5 or abs(missing_diff) >= 1:
            print(f"\n{r['file']}:")
            print(f"  Spacing: GitHub={gh['spacing_issues']}, Local={loc['spacing_issues']} (diff: {spacing_diff:+d})")
            print(f"  Missing: GitHub={gh['missing_options']}, Local={loc['missing_options']} (diff: {missing_diff:+d})")

if __name__ == "__main__":
    main()
