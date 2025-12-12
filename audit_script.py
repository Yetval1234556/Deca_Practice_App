
import sys
import os
from pathlib import Path
from app import _parse_pdf_source

TESTS_DIR = Path("tests")

def run_audit():
    print(f"Scanning {TESTS_DIR.absolute()}...")
    if not TESTS_DIR.exists():
        print("Test directory not found!")
        return

    files = list(TESTS_DIR.glob("*.pdf"))
    print(f"Found {len(files)} PDF files.")
    
    issues = []
    
    for f in files:
        print(f"Checking {f.name}...", end=" ", flush=True)
        try:
            parsed = _parse_pdf_source(f, f.stem)
            qs = parsed.get("questions", [])
            count = len(qs)
            
            if count == 0:
                print("FAILED (0 questions)")
                issues.append(f"{f.name}: 0 questions parsed")
                continue
                
            # Deep check for zero options or missing answers
            zero_opts = 0
            bad_parse = 0
            for q in qs:
                if not q.get("options") or len(q["options"]) < 2:
                    zero_opts += 1
                if "parse failed" in q.get("explanation", "").lower():
                    bad_parse += 1
            
            status_parts = []
            if zero_opts: status_parts.append(f"{zero_opts} no-options")
            if bad_parse: status_parts.append(f"{bad_parse} missing-key")
            
            if status_parts:
                print(f"WARN ({', '.join(status_parts)})")
                issues.append(f"{f.name}: {', '.join(status_parts)}")
            else:
                print(f"OK ({count} q)")
                
        except Exception as e:
            print(f"CRASH: {e}")
            issues.append(f"{f.name}: CRASH {e}")

    print("\n--- Summary ---")
    if not issues:
        print("ALL TESTS PASSED. System is clean.")
    else:
        print(f"Found {len(issues)} issues:")
        for i in issues:
            print(f" - {i}")

if __name__ == "__main__":
    run_audit()
