"""Make one local API request using the generated demo key; prints no credentials."""

import json
import urllib.request

from dotenv import dotenv_values

key = dotenv_values(".env").get("DEMO_API_KEY")
if not key:
    raise SystemExit("Run python scripts/bootstrap.py first.")
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/analyses",
    data=json.dumps(
        {"question": "why did sales change last month", "as_of": "2026-09-22"}
    ).encode(),
    headers={"X-API-Key": key, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=35) as response:
    print(json.dumps(json.load(response), indent=2))
