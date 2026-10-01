import sys
from pathlib import Path

import fakeredis
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import queries  # noqa: E402
import load_redis  # noqa: E402


@pytest.fixture(scope="session")
def fake_redis():
    """A fakeredis instance loaded with the real CSVs (no RediSearch)."""
    r = fakeredis.FakeRedis(decode_responses=True)
    load_redis.load_all(r)
    return r


@pytest.fixture()
def client(fake_redis, monkeypatch):
    monkeypatch.setattr(queries.core, "get_redis", lambda: fake_redis)
    import app as app_module
    monkeypatch.setattr(app_module, "get_redis", lambda: fake_redis)
    queries.dashboard._dash_cache.update(at=0.0, data=None)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
