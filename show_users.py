import sqlite3
import time
import os
import sys
import requests
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

def is_bot(ua):
    """Check if User-Agent looks like a bot."""
    if not ua: return False
    ua = ua.lower()
    bot_keywords = [
        "bot", "crawl", "spider", "slurp", "facebook", "google", 
        "bing", "yahoo", "yandex", "baidu", "duckduck", "curl", 
        "python", "wget", "http-client"
    ]
    return any(keyword in ua for keyword in bot_keywords)

def get_location(ip):
    """Get location from IP using free API."""
    if ip in ("127.0.0.1", "localhost", "::1"):
        return "Localhost"
    if ip.startswith("10.") or ip.startswith("192.168."):
        return "Internal Network"
        
    try:
        # Using ip-api.com (free, no key, 45 requests/min limit)
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                city = data.get("city", "Unknown City")
                region = data.get("regionName", "")
                country = data.get("country", "Unknown Country")
                return f"{city}, {region} ({country})"
    except Exception:
        pass
    return "Unknown Location"

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
        
        # Filter bots and process data
        humans = []
        for ip, ua, last_seen in rows:
            if not is_bot(ua):
                humans.append((ip, ua, last_seen))
        
        print(f"\n👥 Active Users (Last 24 Hours): {len(humans)} (Bots Hidden)")
        print("-" * 80)
        print(f"{'Location':<35} | {'Last Seen':<10} | {'OS / Browser'}")
        print("-" * 80)
        
        for ip, ua, last_seen in humans:
            time_str = datetime.fromtimestamp(last_seen).strftime('%H:%M:%S')
            os_browser = get_os_browser(ua)
            location = get_location(ip)
            
            print(f"{location:<35} | {time_str:<10} | {os_browser}")
            # Truncate UA for display, kept for debug if needed but not prominent
            # print(f"   └─ UA: {ua[:60]}...") 
            print("-" * 80)
            
        if len(rows) - len(humans) > 0:
            print(f"\nℹ️  Filtered {len(rows) - len(humans)} bot(s).")
            
        conn.close()
    except Exception as e:
        print(f"❌ Error reading database: {e}")

if __name__ == "__main__":
    show_active_users()
