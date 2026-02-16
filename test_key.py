#!/usr/bin/env python3
"""Quick test of the new Gemini API key with timeout."""
import urllib.request, json, socket

key = "AIzaSyCEWqsCS58ZfjgHWmgB1Q-FE4kGCNxXXh8"
models = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]

for model in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    data = json.dumps({"contents": [{"parts": [{"text": "Say hi"}]}]}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    print(f"\n--- {model} ---")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.load(r)
            text = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"  200 OK: {text}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            status = err.get("error", {}).get("status", "?")
            msg = err.get("error", {}).get("message", "")
            is_free = "free_tier" in msg.lower() or "freetier" in msg.lower()
            print(f"  HTTP {e.code} ({status})")
            print(f"  {msg[:200]}")
            if is_free:
                print("  >>> STILL FREE TIER <<<")
            else:
                print("  >>> Paid tier rate limit (per-minute) <<<")
        except:
            print(f"  HTTP {e.code}: {body[:200]}")
    except socket.timeout:
        print("  TIMEOUT (15s) - request hung, likely queued by Google")
    except Exception as e:
        print(f"  Error: {e}")

print("\nDone.")
