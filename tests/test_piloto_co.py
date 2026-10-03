"""El piloto CO se carga junto al seed ES y /v1/revisar cita esos artículos."""

from collections import Counter

from tests.conftest import AUTH

CORPUS_KEYS = ("parrafo_exacto", "cita_formal", "enlace_profundo", "chunk_id")
NONSENSE = "Los dragones del consejo tributan en la luna cada martes violeta"


def _revisar(client, **body):
    return client.post("/v1/revisar", json=body, headers=AUTH)


def test_arranque_carga_piloto_co_junto_al_seed_es(app):
    chunks = app.state.local_store.all_chunks()
    co = [chunk for chunk in chunks if chunk.jurisdiccion == "CO"]
    es = [chunk for chunk in chunks if chunk.jurisdiccion == "ES"]
    assert len(co) == 4185
    assert es
    fuentes = Counter(chunk.metadatos.get("fuente") for chunk in co)
    assert fuentes == {
        "CP.md": 384,
        "CC.md": 1837,
        "CGP.md": 625,
        "CST.md": 491,
        "LEY-599-2000.md": 567,
        "LEY-1952-2019.md": 281,
    }
    cp = app.state.local_store.get("co-cp-art-29")
    assert cp is not None
    assert cp.cita_formal.startswith("Constitución")
    assert not cp.cita_formal.startswith("[FIXTURE]")
    assert cp.metadatos["corte"] == "2026-09-27"
    assert "debido proceso" in cp.parrafo.lower()
    for chunk in co:
        assert not chunk.cita_formal.startswith("[FIXTURE]")
        assert not chunk.cita_formal.startswith("[WEKNORA]")
    jornada = app.state.local_store.get("fix-et-034-jornada")
    assert jornada is not None
    assert jornada.jurisdiccion == "ES"
    assert jornada.cita_formal.startswith("[FIXTURE]")


def test_constitucion_art_29_devuelve_el_chunk_colombiano(client):
    response = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"id": "debido", "texto": "Constitución art. 29"}],
    )
    assert response.status_code == 200, response.text
    item = response.json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == "co-cp-art-29"
    assert item["cita_formal"].startswith("Constitución")
    assert not item["cita_formal"].startswith("[FIXTURE]")
    assert "funcionpublica" in item["enlace_profundo"]
    assert "debido proceso" in item["parrafo_exacto"].lower()
    assert item["parrafo_exacto"] not in item["texto"]


def test_sin_jurisdiccion_el_articulo_29_sigue_en_el_corpus(client):
    data = _revisar(
        client,
        afirmaciones=[{"texto": "Constitución art. 29"}],
    ).json()
    assert data["jurisdiccion"] is None
    item = data["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == "co-cp-art-29"
    assert item["cita_formal"].startswith("Constitución")


def test_tesis_sin_norma_en_el_piloto_es_no_sostiene(client):
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"texto": NONSENSE}],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    assert "supera el umbral" in item["indicacion"]
    for key in CORPUS_KEYS:
        assert key not in item
    assert "[FIXTURE]" not in item["indicacion"]
    assert "Constitución" not in item["indicacion"]


def test_articulo_sin_texto_no_se_completa(client, app):
    vacio = app.state.local_store.get("co-cc-art-10")
    assert vacio is not None
    assert not (vacio.parrafo or "").strip()
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"texto": "Código Civil, art. 10"}],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    for key in CORPUS_KEYS:
        assert key not in item


def test_jurisdiccion_co_no_publica_la_fixture_espanola(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"texto": "Estatuto de los Trabajadores, art. 34.1"}],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    assert chunk.cita_formal.startswith("[FIXTURE]")
    for key in CORPUS_KEYS:
        assert key not in item
