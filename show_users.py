import sqlite3
import time
import os
import sys
from pathlib import Path
from datetime import datetime

# Path relative to where script is run, usually root of project
DB_PATH = Path("instance/sessions/sessions.db").resolve()

def get_os_browser(ua):
    """Simple heuristic to parse User-Agent string."""
    ua = ua.lower()
    os_name = "Unknown OS"
    browser_name = "Unknown Browser"
    
    if "windows" in ua: os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua: os_name = "macOS"
    elif "linux" in ua: os_name = "Linux"
    elif "android" in ua: os_name = "Android"
    elif "ios" in ua or "iphone" in ua or "ipad" in ua: os_name = "iOS"
    
    if "chrome" in ua and "edge" not in ua: browser_name = "Chrome"
    elif "firefox" in ua: browser_name = "Firefox"
    elif "safari" in ua and "chrome" not in ua: browser_name = "Safari"
    elif "edge" in ua: browser_name = "Edge"
    elif "curl" in ua: browser_name = "cURL"
    elif "python" in ua: browser_name = "Python Script"
    
    return f"{os_name} / {browser_name}"

def show_active_users():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Cleanup old users first (handling it here ensures accurate read)
        threshold = time.time() - 86400 # 24 hours
        cur.execute("DELETE FROM active_users WHERE last_seen < ?", (threshold,))
        conn.commit()
        
        cur.execute("SELECT ip, ua, last_seen FROM active_users ORDER BY last_seen DESC")
        rows = cur.fetchall()
        
        print(f"\n👥 Active Users (Last 24 Hours): {len(rows)}")
        print("-" * 80)
        print(f"{'IP Address':<15} | {'Last Seen':<20} | {'OS / Browser'}")
        print("-" * 80)
        
        for ip, ua, last_seen in rows:
            time_str = datetime.fromtimestamp(last_seen).strftime('%H:%M:%S')
            os_browser = get_os_browser(ua)
            print(f"{ip:<15} | {time_str:<20} | {os_browser}")
            print(f"   └─ UA: {ua[:60]}...") # Truncate UA for display
            print("-" * 80)
            
        conn.close()
    except Exception as e:
        print(f"❌ Error reading database: {e}")

if __name__ == "__main__":
    show_active_users()
