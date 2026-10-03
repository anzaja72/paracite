from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PARACITE_DEMO_API_KEY", "pc_demo_dev_key")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("ENABLE_INGEST", "false")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("WEKNORA_URL", "")
os.environ.setdefault("JEV_API_KEY", "")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
# Los tests no descargan pesos de Laya. El mock se inyecta en el servicio.
os.environ.setdefault("PARACITE_LAYA", "off")

from paracite.config import get_settings  # noqa: E402
from paracite.main import create_app  # noqa: E402

AUTH = {"Authorization": "Bearer pc_demo_dev_key"}


@pytest.fixture
def app():
    get_settings.cache_clear()
    return create_app(get_settings())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
