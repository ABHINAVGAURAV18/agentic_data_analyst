import hashlib
import json

import pytest

from analyst.config import Settings
from analyst.seed import seed


@pytest.fixture
async def settings(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await seed(url)
    return Settings(
        _env_file=None,
        warehouse_url=url,
        audit_url=url,
        api_key_hashes=json.dumps(
            {
                hashlib.sha256(b"test-key").hexdigest(): "acme",
                hashlib.sha256(b"other-key").hexdigest(): "other",
            }
        ),
    )
