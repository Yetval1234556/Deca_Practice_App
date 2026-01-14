#!/usr/bin/env python3
"""
Analyze REAL spacing issues - not possessives/contractions.
"""

import re
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from app import (
    _extract_clean_lines,
    _parse_answer_key,
    _smart_parse_questions
)

# Known valid short words that should NOT be merged
VALID_SHORT = {
    'a', 'i', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 
    'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 
    'us', 'we', 're', 'vs', 'ok', 'ex', 'id', 'tv', 'uk', 'us', 'dc', 'pc',
    'am', 'pm', 'ad', 'bc', 'hr', 'mr', 'ms', 'dr', 'st', 'nd', 'rd', 'th'
}

def extract_real_issues(text: str) -> list:
    """Extract REAL spacing issues, excluding valid patterns"""
    issues = []
    
    # Pattern 1: Prefix splits (1-2 chars + space + 3+ chars)
    # EXCLUDE: possessives/contractions that end with 's or 't
    for m in re.finditer(r'\b([a-zA-Z]{1,2})\s+([a-zA-Z]{3,})\b', text):
        prefix = m.group(1)
        suffix = m.group(2)
        start = m.start()
        
        # Skip if preceded by apostrophe (possessive/contraction)
        if start > 0 and text[start-1] == "'":
            continue
            
        # Skip valid short words
        if prefix.lower() in VALID_SHORT:
            continue
            
        # This is a real issue
        issues.append(('prefix', f"{prefix} {suffix}", prefix + suffix))
    
    # Pattern 2: Suffix splits (3+ chars + space + 1-2 chars)
    for m in re.finditer(r'\b([a-zA-Z]{3,})\s+([a-zA-Z]{1,2})\b', text):
        prefix = m.group(1)
        suffix = m.group(2)
        
        # Skip valid short words as suffix
        if suffix.lower() in VALID_SHORT:
            continue
            
        # Skip answer options
        if suffix in {'A', 'B', 'C', 'D', 'E'}:
            continue
            
        # This is a real issue
        issues.append(('suffix', f"{prefix} {suffix}", prefix + suffix))
    
    # Pattern 3: -ity/-ly/-ic splits specifically
    for m in re.finditer(r'\b(\w+)\s+(y|ly|ty|ic|ity)\b', text, re.IGNORECASE):
        word = m.group(1)
        ending = m.group(2)
        # These are almost always broken words
        issues.append(('ending', f"{word} {ending}", word + ending))
    
    return issues

def main():
    tests_dir = Path("tests")
    pdfs = sorted(tests_dir.glob("*.pdf"), key=lambda x: int(x.stem) if x.stem.isdigit() else 999)
    
    all_issues = []
    issue_counter = Counter()
    
    print(f"Analyzing {len(pdfs)} PDFs for REAL spacing issues...\n")
    
    for pdf in pdfs[:20]:  # Sample first 20
        try:
            lines = _extract_clean_lines(pdf)
            answers = _parse_answer_key(lines)
            questions = _smart_parse_questions(lines, answers)
            
            for q in questions:
                for field in [q["question"]] + q["options"] + [q["explanation"]]:
                    issues = extract_real_issues(field)
                    all_issues.extend(issues)
                    for issue_type, pattern, merged in issues:
                        issue_counter[pattern.lower()] += 1
                        
        except Exception as e:
            print(f"Error on {pdf.name}: {e}")
    
    print("=" * 70)
    print("TOP 100 REAL SPACING ISSUES (after excluding possessives)")
    print("=" * 70)
    for pattern, count in issue_counter.most_common(100):
        parts = pattern.split()
        if len(parts) == 2:
            merged = parts[0] + parts[1]
            print(f"  {count:5d}x  '{pattern}' -> '{merged}'")
    
    print(f"\n\nTotal REAL issues found in sample: {len(all_issues)}")
    print(f"Unique patterns: {len(issue_counter)}")

if __name__ == "__main__":
    main()
