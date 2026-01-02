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

def get_location_data(ip):
    """Get rich location data from IP including ISP."""
    if ip in ("127.0.0.1", "localhost", "::1"):
        return {"location": "Localhost", "isp": "Loopback"}
    if ip.startswith("10.") or ip.startswith("192.168."):
        return {"location": "Internal Network", "isp": "Private"}
        
    try:
        # Using ip-api.com (free, no key, 45 requests/min limit)
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                city = data.get("city", "Unknown City")
                region = data.get("regionName", "")
                country = data.get("country", "Unknown Country")
                isp = data.get("isp", "") + " " + data.get("org", "")
                return {
                    "location": f"{city}, {region} ({country})",
                    "isp": isp
                }
    except Exception:
        pass
    return {"location": "Unknown Location", "isp": "Unknown ISP"}

def is_hosting_provider(isp_str):
    """Check if ISP indicates a hosting provider/data center."""
    if not isp_str: return False
    isp_str = isp_str.lower()
    
    # Common cloud/hosting providers that suggest non-human traffic
    hosting_keywords = [
        "google", "amazon", "aws", "microsoft", "azure", 
        "digitalocean", "hetzner", "alibaba", "tencent", "oracle", 
        "linode", "ovh", "vultr", "choopa", "leaseweb", "datacenter", 
        "hosting", "cloud", "server", "colocation", "m247", "fly.io"
    ]
    
    return any(keyword in isp_str for keyword in hosting_keywords)

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
        bots_count = 0
        hosting_count = 0
        
        print("🔍 Analyzing traffic sources...")
        
        for ip, ua, last_seen in rows:
            if is_bot(ua):
                bots_count += 1
                continue
                
            loc_data = get_location_data(ip)
            isp = loc_data.get("isp", "")
            
            if is_hosting_provider(isp):
                # Detected as Data Center/Cloud traffic
                hosting_count += 1
                continue
                
            humans.append((ip, ua, last_seen, loc_data))
        
        print(f"\n👥 Real Users (Last 24 Hours): {len(humans)}")
        print(f"   (Filtered: {bots_count} Bots, {hosting_count} Data Center/VPN IPs)")
        print("-" * 135)
        print(f"{'Location':<35} | {'ISP':<30} | {'Last Seen (Date/Time)':<25} | {'OS / Browser'}")
        print("-" * 135)
        
        for ip, ua, last_seen, loc_data in humans:
            # Format: YYYY-MM-DD HH:MM:SS
            time_str = datetime.fromtimestamp(last_seen).strftime('%Y-%m-%d %H:%M:%S')
            os_browser = get_os_browser(ua)
            location = loc_data["location"]
            isp = loc_data.get("isp", "Unknown")
            
            # Truncate ISP if too long
            if len(isp) > 28:
                isp = isp[:25] + "..."
            
            print(f"{location:<35} | {isp:<30} | {time_str:<25} | {os_browser}")
            print("-" * 135)
            
        conn.close()
    except Exception as e:
        print(f"❌ Error reading database: {e}")

if __name__ == "__main__":
    show_active_users()
