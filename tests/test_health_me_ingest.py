from paracite.config import get_settings
from paracite.main import create_app
from tests.conftest import AUTH


def test_ingest_enabled_202(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_INGEST", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ing.db")
    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    app = create_app(get_settings())
    with TestClient(app) as client:
        response = client.post(
            "/v1/ingest",
            headers=AUTH,
            json={"titulo": "Anexo fixture", "texto": "Texto de demostración"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
    get_settings.cache_clear()


def test_corpus_deep_link(client):
    response = client.get("/corpus/fix-et-054-despido-disciplinario")
    assert response.status_code == 200
    assert response.json()["etiqueta_fixture"] is True
