"""Corpus colombiano: procesador de Función Pública, versionado y consulta de artículos."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paracite.config import Settings
from paracite.ingest.cargar import cargar_norma
from paracite.ingest.fuentes.funcionpublica import decodificar, procesar
from paracite.ingest.modelo import NormaCatalogo
from paracite.main import create_app

from .conftest import AUTH

FIXTURE = Path(__file__).parent / "fixtures" / "funcionpublica_cp_extracto.html"
CP = NormaCatalogo(sigla="CP", nombre="Constitución Política de Colombia", cita="Constitución Política",
                   materia="constitucional", fuente="funcionpublica", norma_id="4125")


@pytest.fixture(scope="module")
def articulos():
    return {a.numero: a for a in procesar(decodificar(FIXTURE.read_bytes()))}


def test_procesa_articulos_y_texto_limpio(articulos):
    assert {"1", "2", "64", "178A"} <= set(articulos)
    art1 = articulos["1"].texto
    assert art1.startswith("Colombia es un Estado social de derecho")
    # los bloques ocultos no se cuelan en el texto vigente
    assert "Jurisprudencia Vigencia" not in art1 and "Ver Ley 388" not in art1
    assert articulos["1"].jurisprudencia  # pero se conservan como metadato


def test_vigencia_y_version_anterior(articulos):
    art64 = articulos["64"]
    assert art64.estado == "modificado"
    assert any("Acto Legislativo 01 de 2023" in n for n in art64.notas_vigencia)
    assert art64.texto_anterior and "Es deber del Estado" in art64.texto_anterior[0]
    assert "campesinado" in art64.texto
    assert articulos["178A"].estado == "inexequible"


def test_ruta_capitulo(articulos):
    assert articulos["64"].ruta[-1].startswith("CAPÍTULO 2. DE LOS DERECHOS SOCIALES")


def test_cargar_versionado_y_proteccion(tmp_path):
    html = FIXTURE.read_bytes()
    r1 = cargar_norma(CP, tmp_path, html=html)
    assert r1["cambios"]["nuevos"] == r1["articulos"] > 20
    frag = json.loads((tmp_path / "CP.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert frag["id"] == "co-cp-art-1" and frag["jurisdiccion"] == "CO"
    assert frag["metadatos"]["fuente_oficial"] is True
    assert frag["enlace_profundo"].endswith("norma.php?i=4125#1")

    # Sin cambios: no se reescribe ni se crea historial
    r2 = cargar_norma(CP, tmp_path, html=html)
    assert r2["cambios"] == {"nuevos": 0, "modificados": 0, "retirados": 0}
    assert not (tmp_path / "historial").exists()

    # Cambio de texto: se registra y se guarda la versión anterior
    cambiado = html.decode("utf-8").replace("Estado social de derecho", "Estado social y democrático de derecho")
    r3 = cargar_norma(CP, tmp_path, html=cambiado.encode("utf-8"))
    assert r3["cambios"]["modificados"] == 1
    assert list((tmp_path / "historial").glob("CP-*.jsonl"))

    # La fuente devuelve muy pocos artículos (error del portal): no se reemplaza el corpus
    antes = (tmp_path / "CP.jsonl").read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="no se reemplaza"):
        cargar_norma(CP, tmp_path, html=b"<html><body><p>Mantenimiento</p></body></html>")
    assert (tmp_path / "CP.jsonl").read_text(encoding="utf-8") == antes


@pytest.fixture
def client_corpus(tmp_path, monkeypatch):
    (tmp_path / "co").mkdir()
    cargar_norma(CP, tmp_path / "co", html=FIXTURE.read_bytes())
    monkeypatch.setenv("PARACITE_CORPUS_DIR", str(tmp_path))
    with TestClient(create_app(Settings())) as c:
        yield c


def test_consulta_articulo_existente(client_corpus):
    r = client_corpus.get("/v1/norma/CP/64", headers=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["existe"] is True and d["estado"] == "modificado"
    assert d["etiqueta_fixture"] is False and d["url_oficial"].endswith("#64")


def test_consulta_articulo_inexistente_y_norma_no_cubierta(client_corpus):
    r = client_corpus.get("/v1/norma/CP/999", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["detail"]["norma_cubierta"] is True
    r = client_corpus.get("/v1/norma/CST/62", headers=AUTH)
    assert r.status_code == 404 and r.json()["detail"]["norma_cubierta"] is False


def test_consulta_requiere_api_key(client_corpus):
    assert client_corpus.get("/v1/norma/CP/1").status_code == 401


def test_cite_no_publica_corpus_real_sin_clasificador(client_corpus):
    # Con el clasificador simulado, el corpus real nunca se presenta como cita validada.
    r = client_corpus.post("/v1/cite", headers=AUTH, json={
        "tesis": "Colombia es un Estado social de derecho", "jurisdiccion": "CO"})
    assert r.status_code == 200 and r.json()["matches"] == []


def test_recarga_en_caliente(tmp_path, monkeypatch):
    from paracite.ingest.programador import recargar_indice

    (tmp_path / "co").mkdir()
    monkeypatch.setenv("PARACITE_CORPUS_DIR", str(tmp_path))
    with TestClient(create_app(Settings())) as c:
        assert c.get("/v1/norma/CP/1", headers=AUTH).status_code == 404
        cargar_norma(CP, tmp_path / "co", html=FIXTURE.read_bytes())  # llega corpus nuevo
        recargar_indice(c.app)
        assert c.get("/v1/norma/CP/1", headers=AUTH).status_code == 200


def _arts(nombre: str):
    ruta = Path(__file__).parent / "fixtures" / nombre
    return {a.numero: a for a in procesar(decodificar(ruta.read_bytes()))}


def test_estatuto_tributario_reinicio_guiones_y_notas():
    arts = _arts("funcionpublica_et_extracto.html")
    # El art. 1 es el del Estatuto (no el del Decreto 624 que lo adopta)
    assert arts["1"].epigrafe.upper().startswith("ORIGEN DE LA OBLIGACI")
    assert arts["1"].texto.startswith("La obligación tributaria sustancial")
    # Artículos con guion, numerales en <ol> y nota de vigencia dentro de un enlace
    a = arts["240-1"]
    assert a.epigrafe == "TARIFA PARA USUARIOS DE ZONA FRANCA"
    assert "La suma de los numerales 1 y 2" in a.texto
    assert a.estado == "modificado" and "Ley 2277 de 2022" in a.notas_vigencia[0]


def test_cst_listas_y_articulo_sin_texto():
    arts = _arts("funcionpublica_cst_extracto.html")
    assert arts["69"].epigrafe.startswith("RESPONSABILIDAD DE LOS")
    assert "responden solidariamente" in arts["69"].texto  # contenido en <ol><li>
    assert arts["360"].estado == "sin_texto_en_fuente" and arts["360"].epigrafe
