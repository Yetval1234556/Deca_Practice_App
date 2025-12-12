
from pathlib import Path
from app import _extract_clean_lines

def debug_key():
    p = Path("tests/2017.pdf")
    if not p.exists():
        print("2017.pdf not found")
        return

    lines = _extract_clean_lines(p)
    print(f"Total lines: {len(lines)}")
    
    # Search for start of key (Question 1)
    import re
    pat = re.compile(r"^\s*1[\s.:]+[A-E]\b", re.IGNORECASE)
    
    found_at = -1
    for i, line in enumerate(lines):
        if pat.search(line):
            print(f"Potential start at line {i}: {line}")
            found_at = i
            # Print context
            for j in range(max(0, i-5), min(len(lines), i+20)):
                print(f"{j}: {lines[j]}")
            break
            
    if found_at == -1:
        print("Could not find '1. A' pattern.")

if __name__ == "__main__":
    debug_key()
