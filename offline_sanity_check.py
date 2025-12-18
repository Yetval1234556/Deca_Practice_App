import sys
from pathlib import Path

# Add current dir to path to import app
sys.path.append(".")

try:
    import app
except ImportError:
    print("Error: Could not import app.py within the current directory.")
    sys.exit(1)

def run():
    print("Starting Offline Sanity Check (Direct PDF Parsing)...")
    
    tests_dir = app.TESTS_DIR
    if not tests_dir.exists():
        print(f"Tests directory not found at {tests_dir}")
        sys.exit(1)
        
    pdf_files = list(tests_dir.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found in tests directory.")
        sys.exit(0)
        
    print(f"Found {len(pdf_files)} PDF files. Verifying...")
    
    failures = []
    
    for pdf_path in pdf_files:
        try:
            # We access the internal function _parse_pdf_source if available
            if hasattr(app, "_parse_pdf_source"):
                test_data = app._parse_pdf_source(pdf_path, pdf_path.stem)
            else:
                # Fallback: replicate the logic
                lines = app._extract_clean_lines(pdf_path)
                answers = app._parse_answer_key(lines)
                questions = app._smart_parse_questions(lines, answers)
                test_data = {"name": pdf_path.stem, "questions": questions}

            name = test_data.get("name")
            questions = test_data.get("questions", [])
            count = len(questions)
            
            if count != 100:
                print(f"[WARN] {name}: {count} questions (Expected 100)")
                failures.append(f"{name}: {count}")
            else:
                # Optional: deep check of Q100 Option D (as per user history)
                q100 = next((q for q in questions if q["number"] == 100), None)
                if q100 and len(q100.get("options", [])) >= 4:
                    opt_d = q100["options"][3]
                    if "Hospitality" in opt_d or "copyright" in opt_d.lower():
                         print(f"[WARN] {name}: Q100 Option D might be dirty: '{opt_d}'")
                         failures.append(f"{name}: Dirty Q100D")
            
        except Exception as e:
            print(f"[ERROR] Failed to parse {pdf_path.name}: {e}")
            failures.append(f"{pdf_path.name}: Exception {e}")

    if failures:
        print(f"\n[FAIL] {len(failures)} tests failed verification.")
        sys.exit(1)
    else:
        print(f"\n[SUCCESS] All {len(pdf_files)} tests verified successfully (100 questions, clean parse).")

if __name__ == "__main__":
    run()
