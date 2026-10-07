import urllib.request
import urllib.error
import json

url = "https://www.pathofexile.com/character-window/get-items?accountName=mikaelzo&character=BOMSHAK"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.pathofexile.com/",
    },
)
try:
    with urllib.request.urlopen(req, timeout=8) as resp:
        print("Status:", resp.status)
        data = resp.read().decode("utf-8")
        print("Data starts with:", data[:100])
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
except Exception as e:
    print("Exception:", type(e), e)
