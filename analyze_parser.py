#!/usr/bin/env python3
"""
Comprehensive parser analysis script.
Analyzes all 71 PDFs to identify edge cases and parsing issues.
"""
import sys
import os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress logging noise
import logging
logging.getLogger().setLevel(logging.ERROR)

from app import _parse_pdf_source

TESTS_DIR = Path(__file__).parent / "tests"

def analyze_all_pdfs():
    """Analyze all PDFs and generate a comprehensive report."""
    pdf_files = sorted(TESTS_DIR.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in tests directory")
        return
    
    print(f"🔍 Analyzing {len(pdf_files)} PDF files...")
    print("=" * 70)
    
    # Statistics
    total_questions = 0
    total_with_issues = 0
    issues = defaultdict(list)
    
    for pdf_path in pdf_files:
        try:
            result = _parse_pdf_source(pdf_path, pdf_path.name)
            questions = result.get("questions", [])
            
            if not questions:
                issues["no_questions"].append(pdf_path.name)
                continue
            
            total_questions += len(questions)
            
            for q in questions:
                q_num = q.get("number", "?")
                prompt = q.get("question", "")
                options = q.get("options", [])  # List of strings
                correct_idx = q.get("correct_index")
                correct_letter = q.get("correct_letter")
                explanation = q.get("explanation", "")
                
                # Check for issues
                q_id = f"{pdf_path.name} Q{q_num}"
                has_issue = False
                
                # 1. Missing or empty prompt
                if not prompt or len(prompt.strip()) < 10:
                    issues["empty_prompt"].append(f"{q_id}: '{prompt[:50] if prompt else 'EMPTY'}...'")
                    has_issue = True
                
                # 2. Missing options (less than 4)
                if len(options) < 4:
                    issues["missing_options"].append(f"{q_id}: Only has {len(options)} options")
                    has_issue = True
                
                # 3. Empty option text
                for i, opt in enumerate(options):
                    opt_text = opt if isinstance(opt, str) else str(opt)
                    if not opt_text.strip() or opt_text == "[Option missing from PDF]":
                        label = chr(ord('A') + i)
                        issues["empty_option"].append(f"{q_id} Opt {label}")
                        has_issue = True
                
                # 4. Missing correct answer
                if correct_idx is None or correct_idx < 0:
                    issues["no_answer"].append(q_id)
                    has_issue = True
                
                # 5. Answer out of range
                if correct_idx is not None and correct_idx >= 0 and correct_idx >= len(options):
                    issues["answer_out_of_range"].append(f"{q_id}: idx={correct_idx}, opts={len(options)}")
                    has_issue = True
                
                # 6. Spacing issues in prompt
                spacing_patterns = [
                    (' w as ', 'was'),
                    (' h as ', 'has'),
                    ('  ', 'double space'),
                    (' t he ', 'the'),
                    (' w ith', 'with'),
                ]
                prompt_lower = prompt.lower() if prompt else ""
                for bad, desc in spacing_patterns:
                    if bad in prompt_lower:
                        issues["spacing_prompt"].append(f"{q_id}: {desc}")
                
                # 7. Spacing issues in options
                for i, opt in enumerate(options):
                    opt_text = opt if isinstance(opt, str) else str(opt)
                    opt_lower = opt_text.lower()
                    for bad, desc in spacing_patterns:
                        if bad in opt_lower:
                            label = chr(ord('A') + i)
                            issues["spacing_option"].append(f"{q_id} Opt {label}: {desc}")
                
                # 8. Very short/missing explanation
                if not explanation or explanation == "No explanation available (Parse failed)":
                    issues["missing_explanation"].append(f"{q_id}")
                elif len(explanation.strip()) < 20:
                    issues["short_explanation"].append(f"{q_id}: '{explanation[:30]}'")
                
                if has_issue:
                    total_with_issues += 1
                
        except Exception as e:
            issues["parse_error"].append(f"{pdf_path.name}: {str(e)[:100]}")
    
    # Print report
    print(f"\n📊 ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Total PDFs analyzed: {len(pdf_files)}")
    print(f"Total questions parsed: {total_questions}")
    print(f"Questions with issues: {total_with_issues}")
    print()
    
    # Sort issues by severity
    issue_order = [
        ("parse_error", "🔴 Parse Errors"),
        ("no_questions", "🔴 No Questions Extracted"),
        ("no_answer", "🔴 Missing Correct Answer"),
        ("answer_out_of_range", "🔴 Answer Index Out of Range"),
        ("missing_options", "🟠 Missing Options (< 4)"),
        ("empty_prompt", "🟠 Empty/Short Prompts"),
        ("empty_option", "🟡 Empty Option Text"),
        ("spacing_prompt", "🟡 Spacing Issues in Prompts"),
        ("spacing_option", "🟡 Spacing Issues in Options"),
        ("missing_explanation", "🔵 Missing Explanation"),
        ("short_explanation", "🔵 Short Explanations"),
    ]
    
    for key, label in issue_order:
        items = issues.get(key, [])
        if items:
            print(f"\n{label} ({len(items)} issues)")
            print("-" * 50)
            for item in items[:10]:  # Show first 10
                print(f"  • {item}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
    
    # Summary
    print("\n" + "=" * 70)
    critical = len(issues.get("parse_error", [])) + len(issues.get("no_questions", [])) + \
               len(issues.get("no_answer", [])) + len(issues.get("answer_out_of_range", []))
    
    if critical > 0:
        print(f"❌ {critical} CRITICAL issues need fixing")
    else:
        print("✅ No critical issues found!")
    
    return issues

if __name__ == "__main__":
    analyze_all_pdfs()
