from paracite.auth.keys import hash_key
from paracite.db.models import ApiKey, User
from tests.conftest import AUTH


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "paracite"


def test_cite_requires_auth(client):
    response = client.post("/v1/cite", json={"tesis": "hola"})
    assert response.status_code == 401


def test_me_with_demo_key(client):
    response = client.get("/v1/me", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["nombre"] == "demo"
    assert body["plan"] == "mvp"
    assert body["rate_limit"]["limit"] >= 1


def test_invalid_key(client):
    response = client.get("/v1/me", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_rate_limit_429(app, client):
    db = app.state.SessionLocal()
    user = db.query(User).first()
    raw = "pc_low_limit_key"
    db.add(
        ApiKey(
            user_id=user.id,
            name="low",
            key_prefix="pc_low",
            key_hash=hash_key(raw),
            rate_limit_per_minute=1,
            active=True,
        )
    )
    db.commit()
    db.close()
    headers = {"Authorization": f"Bearer {raw}"}
    first = client.get("/v1/me", headers=headers)
    assert first.status_code == 200
    second = client.get("/v1/me", headers=headers)
    assert second.status_code == 429


def test_ingest_stub_501(client):
    response = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"titulo": "doc", "texto": "párrafo fixture"},
    )
    assert response.status_code == 501
