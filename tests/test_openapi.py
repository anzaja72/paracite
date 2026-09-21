from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_openapi_contains_mvp_paths(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/v1/cite" in paths
    assert "/health" in paths
    assert "/v1/me" in paths
    assert "/v1/ingest" in paths
    cite = paths["/v1/cite"]["post"]
    body = cite["requestBody"]["content"]["application/json"]["schema"]
    # FastAPI may inline or $ref
    dumped = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "openapi.yaml").write_text(dumped, encoding="utf-8")
    assert "tesis" in dumped
    assert "umbral_confianza" in dumped
    assert "sin_match_alta_confianza" in dumped


def test_docs_ui(client):
    response = client.get("/docs")
    assert response.status_code == 200
