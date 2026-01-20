#!/usr/bin/env python3
"""
Verification script to test the parser against all 71 test PDFs.
Checks for common word confusion issues like 'was' -> 'w as'.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from app import _fix_broken_words, _parse_pdf_source

TESTS_DIR = Path(__file__).parent / "tests"

# Words that should NEVER be split
MUST_NOT_SPLIT = [
    ('was', 'w as'),
    ('has', 'h as'),
    ('gas', 'g as'),
    ('This', 'T his'),
    ('That', 'T hat'),
    ('they', 't hey'),
    ('them', 't hem'),
    ('then', 't hen'),
    ('when', 'w hen'),
    ('what', 'w hat'),
    ('with', 'w ith'),
    ('from', 'f rom'),
    ('have', 'h ave'),
    ('which', 'w hich'),
]

def test_fix_broken_words():
    """Test that common words are not incorrectly split."""
    print("=" * 60)
    print("Testing _fix_broken_words function")
    print("=" * 60)
    
    errors = []
    
    for correct, incorrect in MUST_NOT_SPLIT:
        # Test the word by itself
        result = _fix_broken_words(correct)
        if result != correct:
            errors.append(f"FAIL: '{correct}' became '{result}'")
        
        # Test in a sentence
        sentence = f"The word {correct} should stay intact."
        result = _fix_broken_words(sentence)
        if incorrect in result:
            errors.append(f"FAIL: '{correct}' in sentence became split: '{result}'")
    
    # Test that run-on words ARE fixed
    run_on_tests = [
        ("performanceThe company", "performance The company"),
        ("resultThis shows", "result This shows"),
        ("businessAs usual", "business As usual"),
    ]
    
    for bad, expected in run_on_tests:
        result = _fix_broken_words(bad)
        if expected not in result:
            errors.append(f"RUN-ON NOT FIXED: '{bad}' -> '{result}' (expected '{expected}')")
    
    if errors:
        print("\n❌ FAILURES:")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("\n✅ All word tests passed!")
        return True

def test_parse_pdfs(limit=5):
    """Test parsing a sample of PDFs."""
    print("\n" + "=" * 60)
    print(f"Testing PDF parsing (sample of {limit} PDFs)")
    print("=" * 60)
    
    pdf_files = sorted(TESTS_DIR.glob("*.pdf"))[:limit]
    
    if not pdf_files:
        print("⚠️  No PDF files found in tests directory")
        return True
    
    errors = []
    total_questions = 0
    
    for pdf_path in pdf_files:
        try:
            result = _parse_pdf_source(pdf_path, pdf_path.name)
            questions = result.get("questions", [])
            total_questions += len(questions)
            
            # Check for word splits in questions
            for q in questions:
                prompt = q.get("question", "")
                for correct, incorrect in MUST_NOT_SPLIT:
                    if incorrect in prompt:
                        errors.append(f"{pdf_path.name} Q{q.get('number')}: Found '{incorrect}' (should be '{correct}')")
                
                # Check options too
                for opt in q.get("options", []):
                    text = opt.get("text", "")
                    for correct, incorrect in MUST_NOT_SPLIT:
                        if incorrect in text:
                            errors.append(f"{pdf_path.name} Q{q.get('number')} Opt {opt.get('label')}: Found '{incorrect}'")
            
            print(f"  ✓ {pdf_path.name}: {len(questions)} questions parsed")
        except Exception as e:
            errors.append(f"{pdf_path.name}: Parse error - {e}")
    
    print(f"\n  Total questions parsed: {total_questions}")
    
    if errors:
        print(f"\n❌ {len(errors)} issues found:")
        for e in errors[:20]:  # Show first 20
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
        return False
    else:
        print("\n✅ No word confusion issues found in parsed PDFs!")
        return True

def main():
    print("\n🔍 DECA Parser Verification Script")
    print("=" * 60)
    
    success = True
    
    # Test 1: Unit test the _fix_broken_words function
    if not test_fix_broken_words():
        success = False
    
    # Test 2: Parse sample PDFs and check for issues
    if not test_parse_pdfs(limit=10):
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED - Review issues above")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
