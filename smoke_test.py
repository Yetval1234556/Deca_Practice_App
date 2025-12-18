import requests
import sys
import time

BASE_URL = "http://127.0.0.1:8080"

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def test_homepage():
    try:
        r = requests.get(f"{BASE_URL}/")
        if r.status_code == 200:
            log("Homepage load: PASS", "SUCCESS")
            return True
        else:
            log(f"Homepage load: FAIL (Status {r.status_code})", "ERROR")
            return False
    except Exception as e:
        log(f"Homepage load: FAIL ({e})", "ERROR")
        return False

def test_static_assets():
    assets = ["/static/style.css", "/static/app.js", "/static/favicon.png"]
    all_pass = True
    for asset in assets:
        try:
            r = requests.get(f"{BASE_URL}{asset}")
            if r.status_code == 200:
                log(f"Asset '{asset}': PASS", "SUCCESS")
            elif r.status_code == 304:
                log(f"Asset '{asset}': PASS (Cached)", "SUCCESS")
            else:
                log(f"Asset '{asset}': FAIL (Status {r.status_code})", "ERROR")
                all_pass = False
        except Exception as e:
            log(f"Asset '{asset}': FAIL ({e})", "ERROR")
            all_pass = False
    return all_pass

def test_api_tests_endpoint():
    try:
        r = requests.get(f"{BASE_URL}/api/tests")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log(f"API Tests list: PASS (Found {len(data)} tests)", "SUCCESS")
                return True
            else:
                log("API Tests list: FAIL (Invalid JSON structure)", "ERROR")
                return False
        else:
            log(f"API Tests list: FAIL (Status {r.status_code})", "ERROR")
            return False
    except Exception as e:
        log(f"API Tests list: FAIL ({e})", "ERROR")
        return False

def run_tests():
    log("Starting Smoke Screen Tests...", "INFO")
    
    # Wait a moment to ensure server is ready if just started (though it's running in background)
    try:
        requests.get(BASE_URL, timeout=2)
    except:
        log("Server not reachable immediately, waiting 2s...", "WARN")
        time.sleep(2)

    results = [
        test_homepage(),
        test_static_assets(),
        test_api_tests_endpoint()
    ]
    
    if all(results):
        log("ALL SMOKE TESTS PASSED", "SUCCESS")
        sys.exit(0)
    else:
        log("SOME SMOKE TESTS FAILED", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
