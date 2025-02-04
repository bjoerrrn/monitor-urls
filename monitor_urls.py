#!/usr/bin/env python3

# v1.0.0
# monitor_urls - by bjoerrrn
# github: https://github.com/bjoerrrn/monitor_urls
# This script is licensed under GNU GPL version 3.0 or above

import os
import json
import requests
import shlex
import urllib3
from bs4 import BeautifulSoup  # For better keyword detection
from urllib.parse import urlparse

# Suppress SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_urls.credo")
FAILURE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "failures.json")
FAILURE_THRESHOLD = 5
TIMEOUT = 10  # Increased timeout for local IPs

# Load failure counts from a file
def load_failures():
    if os.path.exists(FAILURE_FILE):
        try:
            with open(FAILURE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[ERROR] Failed to parse failures.json, resetting...")
            return {}
    return {}

# Save failure counts to a file
def save_failures(failures):
    with open(FAILURE_FILE, "w") as f:
        json.dump(failures, f)

# Persistent failure tracking
failure_counts = load_failures()
recovery_sent = {}

def is_local_ip(url):
    """Returns True if the URL is a local network IP (192.168.x.x or similar)."""
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    return hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.endswith(".local")

def load_urls():
    """Load URLs, webhooks, descriptions, and optional keywords from the config file."""
    urls = []
    if not os.path.exists(CONFIG_FILE):
        print(f"[ERROR] Config file {CONFIG_FILE} not found.")
        return urls
    
    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = shlex.split(line)
                    if len(parts) < 3:  # Require at least description, URL, and webhook
                        continue
                    description, url, webhook = parts[:3]
                    keyword = parts[3] if len(parts) > 3 else None
                    urls.append({"description": description, "url": url, "webhook": webhook, "keyword": keyword})
    except Exception as e:
        print(f"[ERROR] Loading config: {e}")
    
    return urls

def check_url(url):
    """Checks if a URL is reachable and returns the HTML content."""
    try:
        verify_ssl = not is_local_ip(url)  # Disable SSL verification for local IPs
        print(f"[DEBUG] Checking {url} (SSL Verification: {verify_ssl})...")
        response = requests.get(url, timeout=TIMEOUT, verify=verify_ssl)
        print(f"[DEBUG] {url} status: {response.status_code}")
        if response.status_code == 200:
            return True, response.text
        return False, None
    except requests.RequestException as e:
        print(f"[ERROR] Failed to reach {url}: {e}")
        return False, None

def keyword_found(content, keyword):
    """Checks if the keyword exists in the page content (ignoring HTML tags and case)."""
    if not content or not keyword:
        return False

    keyword = keyword.lower()
    soup = BeautifulSoup(content, "html.parser")
    text_only = soup.get_text().lower()

    return keyword in text_only

def notify_discord(webhook, message):
    """Sends a notification to Discord and prints it."""
    print(f"[NOTIFY] {message}")  # Print for debugging
    try:
        requests.post(webhook, json={"content": message})
    except requests.RequestException as e:
        print(f"[ERROR] Discord notification failed: {e}")

def monitor():
    """Monitors URLs, sending alerts on failures and recoveries."""
    global failure_counts, recovery_sent
    urls = load_urls()
    
    for entry in urls:
        description = entry["description"]
        url = entry["url"]
        webhook = entry["webhook"]
        keyword = entry["keyword"]

        reachable, content = check_url(url)

        keyword_missing = keyword and reachable and not keyword_found(content, keyword)

        if not reachable or keyword_missing:
            failure_counts[url] = failure_counts.get(url, 0) + 1
            print(f"[WARNING] {description} ({url}) failure count: {failure_counts[url]}/{FAILURE_THRESHOLD}")

            if failure_counts[url] >= FAILURE_THRESHOLD:
                if not recovery_sent.get(url, False):
                    if not reachable:
                        msg = f"❌ {description} ({url}) DOWN"
                    elif keyword_missing:
                        msg = f"⚠️ {description} ({url}) MISSING '{keyword}'"
                    notify_discord(webhook, msg)
                    recovery_sent[url] = True  # Prevent multiple alerts
        else:
            if failure_counts.get(url, 0) >= FAILURE_THRESHOLD:
                notify_discord(webhook, f"✅ {description} ({url}) UP")
            print(f"[INFO] {description} ({url}) is UP (Failures Reset).")
            failure_counts[url] = 0
            recovery_sent[url] = False

    # Save failure counts to disk after each run
    save_failures(failure_counts)

if __name__ == "__main__":
    monitor()
