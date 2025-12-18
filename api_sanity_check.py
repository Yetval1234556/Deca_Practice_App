import requests
import sys

BASE_URL = "http://127.0.0.1:8080"

def run_sanity_check():
    print(f"Starting API Sanity Check against {BASE_URL}...")
    
    # 1. Fetch Test List
    try:
        r = requests.get(f"{BASE_URL}/api/tests")
        if r.status_code != 200:
            print(f"[FAIL] Could not fetch tests. Status: {r.status_code}")
            sys.exit(1)
        
        tests = r.json()
        print(f"[INFO] Found {len(tests)} tests.")
        
        failures = []
        
        # 2. Check each test
        for t in tests:
            t_id = t.get("id")
            name = t.get("name")
            count = t.get("question_count")
            
            if count != 100:
                print(f"[WARN] Test '{name}' ({t_id}) has {count} questions (Expected 100).")
                failures.append(f"{name}: {count} questions")
            
            # Optional: We could try to start a quiz for each to ensure it loads
            # but that might be slow for 54 tests. Spot checking might be better.
            
        if failures:
            print(f"\n[FAIL] {len(failures)} tests failed the question count check.")
            sys.exit(1)
        else:
            print(f"[SUCCESS] All {len(tests)} tests have exactly 100 questions.")
            sys.exit(0)
            
    except Exception as e:
        print(f"[ERROR] Exception during sanity check: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sanity_check()
