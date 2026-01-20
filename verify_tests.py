#!/usr/bin/env python3
"""
Comprehensive parser verification script.
Checks: Q100 option D, 100 questions per test, 4 options, explanations.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.getLogger().setLevel(logging.ERROR)

import importlib
import app
importlib.reload(app)
from app import _parse_pdf_source
from pathlib import Path

TESTS_DIR = Path(__file__).parent / "tests"

def verify_all_tests():
    """Comprehensive verification of all tests."""
    pdf_files = sorted(TESTS_DIR.glob("*.pdf"))
    
    print(f"🔍 Verifying {len(pdf_files)} PDF files...")
    print("=" * 80)
    
    # Track issues
    q100_issues = []
    count_issues = []
    option_issues = []
    explanation_issues = []
    
    for pdf_path in pdf_files:
        result = _parse_pdf_source(pdf_path, pdf_path.name)
        questions = result.get("questions", [])
        
        pdf_name = pdf_path.name
        
        # Check 1: Does it have 100 questions?
        if len(questions) != 100:
            count_issues.append(f"{pdf_name}: {len(questions)} questions (expected 100)")
        
        # Find Q100
        q100 = None
        for q in questions:
            if q.get("number") == 100:
                q100 = q
                break
        
        # Check Q100 option D
        if q100:
            options = q100.get("options", [])
            if len(options) >= 4:
                opt_d = options[3]  # Index 3 = D
                if not opt_d or opt_d == "[Option missing from PDF]" or len(str(opt_d).strip()) < 2:
                    q100_issues.append(f"{pdf_name} Q100 Opt D: EMPTY or MISSING")
                elif "  " in str(opt_d):
                    q100_issues.append(f"{pdf_name} Q100 Opt D: has double spaces: '{opt_d[:50]}'")
                else:
                    # Check for other issues
                    suspicious = False
                    for pattern in [' It', ' If', ' As', ' Er', ' Or', ' Ity']:
                        if pattern in str(opt_d):
                            q100_issues.append(f"{pdf_name} Q100 Opt D: contains '{pattern}': '{opt_d[:60]}'")
                            suspicious = True
                            break
                    if not suspicious:
                        pass  # Clean!
            else:
                q100_issues.append(f"{pdf_name} Q100: Only has {len(options)} options")
        else:
            q100_issues.append(f"{pdf_name}: Q100 not found!")
        
        # Check all questions for 4 options and explanations
        for q in questions:
            q_num = q.get("number", "?")
            options = q.get("options", [])
            explanation = q.get("explanation", "")
            
            # Check option count
            if len(options) != 4:
                option_issues.append(f"{pdf_name} Q{q_num}: {len(options)} options")
            
            # Check explanation
            if not explanation or explanation == "No explanation available (Parse failed)" or len(explanation.strip()) < 10:
                explanation_issues.append(f"{pdf_name} Q{q_num}")
    
    # Print reports
    print("\n📋 QUESTION COUNT VERIFICATION")
    print("-" * 50)
    if count_issues:
        for issue in count_issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All tests have 100 questions")
    
    print(f"\n📋 QUESTION 100 OPTION D VERIFICATION")
    print("-" * 50)
    if q100_issues:
        for issue in q100_issues[:20]:
            print(f"  ❌ {issue}")
        if len(q100_issues) > 20:
            print(f"  ... and {len(q100_issues) - 20} more")
    else:
        print("  ✅ All Q100 Option D are clean")
    
    print(f"\n📋 OPTION COUNT ISSUES (not 4 options)")
    print("-" * 50)
    if option_issues:
        for issue in option_issues[:20]:
            print(f"  ❌ {issue}")
        if len(option_issues) > 20:
            print(f"  ... and {len(option_issues) - 20} more")
        print(f"  Total: {len(option_issues)} questions with wrong option count")
    else:
        print("  ✅ All questions have 4 options")
    
    print(f"\n📋 MISSING EXPLANATIONS")
    print("-" * 50)
    if explanation_issues:
        print(f"  ❌ {len(explanation_issues)} questions missing explanations")
        for issue in explanation_issues[:10]:
            print(f"     • {issue}")
        if len(explanation_issues) > 10:
            print(f"     ... and {len(explanation_issues) - 10} more")
    else:
        print("  ✅ All questions have explanations")
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print(f"  Question count issues: {len(count_issues)}")
    print(f"  Q100 Option D issues: {len(q100_issues)}")
    print(f"  Option count issues: {len(option_issues)}")
    print(f"  Missing explanations: {len(explanation_issues)}")
    
    total = len(count_issues) + len(q100_issues) + len(option_issues) + len(explanation_issues)
    if total == 0:
        print("\n🎉 ALL TESTS PASS!")
    else:
        print(f"\n❌ {total} total issues found")
    
    return {
        "count_issues": count_issues,
        "q100_issues": q100_issues,
        "option_issues": option_issues,
        "explanation_issues": explanation_issues
    }

if __name__ == "__main__":
    verify_all_tests()
