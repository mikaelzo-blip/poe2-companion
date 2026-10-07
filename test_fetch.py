import asyncio
from pathlib import Path
from companion.dashboard_api import fetch_public_profile

res = fetch_public_profile("mikaelzo#5674", "BOMSHAK", Path("."))
print(res)
