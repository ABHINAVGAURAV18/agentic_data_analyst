"""Generate local-only credentials without replacing an existing .env."""

import hashlib
import json
import secrets
from pathlib import Path

path = Path(".env")
if path.exists():
    raise SystemExit(".env exists; preserve it or explicitly remove it before regenerating.")
key = secrets.token_hex(24)
values = {
    "POSTGRES_PASSWORD": secrets.token_hex(24),
    "READER_PASSWORD": secrets.token_hex(24),
    "AUDIT_PASSWORD": secrets.token_hex(24),
    "API_KEY_HASHES": json.dumps({hashlib.sha256(key.encode()).hexdigest(): "acme"}),
    "DEMO_API_KEY": key,
}
path.write_text("\n".join(f"{k}='{v}'" for k, v in values.items()) + "\n")
path.chmod(0o600)
print("Created .env. Use DEMO_API_KEY from that file as X-API-Key. Never commit .env.")
