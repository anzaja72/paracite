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


# ---------------- Secretaría del Senado ----------------

SENADO_CST = Path(__file__).parent / "fixtures" / "senado_cst_parte0.html"


def test_senado_articulos_notas_y_epigrafes():
    from paracite.ingest.fuentes import senado

    arts = {a.numero: a for a in senado.procesar(senado.decodificar(SENADO_CST.read_bytes()))}
    assert "1" in arts and "1O" not in arts
    assert arts["1"].epigrafe == "OBJETO"
    art3 = arts["3"]
    assert art3.estado == "modificado"
    assert any("Ley 2466 de 2025" in n for n in art3.notas_vigencia)
    assert not art3.texto.startswith("<") and "El nuevo texto" not in art3.texto
    assert arts["30"].estado == "derogado"
    assert arts["31"].ruta[-1].startswith("CAPITULO II")


def test_senado_candidatos_y_descarga_por_partes(monkeypatch):
    from paracite.ingest import cargar
    from paracite.ingest.fuentes import senado

    norma = NormaCatalogo(sigla="LEY-100-1993", nombre="Ley 100 de 1993", cita="Ley 100 de 1993",
                          materia="laboral", fuente="senado", tipo="ley", numero="100", anio="1993")
    assert norma.candidatos_senado == ["ley_0100_1993.html"]
    dec = NormaCatalogo(sigla="DEC-780-2016", nombre="Decreto 780 de 2016", cita="Decreto 780 de 2016",
                        materia="salud", fuente="senado", tipo="decreto", numero="780", anio="2016")
    assert dec.candidatos_senado[0] == "decreto_0780_2016.html"

    paginas = {
        senado.url_de("ley_0100_1993.html"):
            b'<p><a class="bookmarkaj" name="1">ARTICULO 1o. OBJETO.</a> Texto uno.</p>'
            b'<p><a class="antsig" href="ley_0100_1993_pr001.html">Siguiente</a></p>',
        senado.url_de("ley_0100_1993_pr001.html"):
            b'<p><a class="bookmarkaj" name="2">ARTICULO 2o. PRINCIPIOS.</a> '
            b'&lt;Art\xedculo modificado por el art\xedculo 1 de la Ley 797 de 2003&gt; Texto dos.</p>',
    }
    monkeypatch.setattr(cargar, "descargar", lambda url, **kw: paginas[url])
    monkeypatch.setattr(cargar.time, "sleep", lambda s: None)
    html, url = cargar.descargar_senado(norma)
    arts = {a.numero: a for a in senado.procesar(html.decode("utf-8"))}
    assert set(arts) == {"1", "2"} and arts["2"].estado == "modificado"
    assert url.endswith("ley_0100_1993.html")


def test_numeracion_dur_y_ordinales():
    from paracite.ingest.fuentes import funcionpublica, senado

    html_fp = """<html><body>
    <p><strong>ARTÍCULO <a id="1.1.1.1"></a>1.1.1.1.</strong> <strong>Objeto.</strong> Compilar las normas.</p>
    <p><strong>ARTÍCULO <a id="2.2.1.1.1"></a>2.2.1.1.1.</strong> Ámbito de aplicación del contrato.</p>
    <p><strong>ARTÍCULO 2.2.1.1.1-1.</strong> Artículo adicionado.</p>
    </body></html>"""
    arts = funcionpublica.procesar(html_fp)
    assert [a.numero for a in arts] == ["1.1.1.1", "2.2.1.1.1", "2.2.1.1.1-1"]
    assert arts[0].epigrafe == "Objeto" and arts[0].texto == "Compilar las normas."

    html_senado = """<html><body>
    <p><a name="1">ARTÍCULO PRIMERO.</a> Apruébese el Acuerdo Regional.</p>
    <p><a name="2">ARTÍCULO SEGUNDO.</a> De conformidad con la Ley 7a de 1944.</p>
    <p><a name="11">ARTÍCULO DÉCIMO PRIMERO.</a> Rige a partir de su publicación.</p>
    </body></html>"""
    arts = senado.procesar(html_senado)
    assert [a.numero for a in arts] == ["1", "2", "11"]
    assert arts[0].texto == "Apruébese el Acuerdo Regional."


def test_identidad_norma_funcionpublica(tmp_path):
    from paracite.ingest.cargar import _verificar_identidad
    from paracite.ingest.modelo import NormaCatalogo

    dur = NormaCatalogo(sigla="DEC-1072-2015", nombre="Decreto 1072 de 2015", cita="Decreto 1072 de 2015",
                        materia="laboral", fuente="funcionpublica", norma_id="72173", tipo="decreto",
                        numero="1072", anio="2015")
    _verificar_identidad(dur, "<title>Decreto 1072 de 2015 Sector Trabajo - Gestor Normativo</title>")
    with pytest.raises(RuntimeError, match="revise el catálogo"):
        _verificar_identidad(dur, "<title>Decreto 1507 de 2015 - Gestor Normativo</title>")


def test_funcionpublica_formatos_antiguos():
    from paracite.ingest.fuentes import funcionpublica

    # Leyes 27 de 1977 y 29 de 1982: exportadas de Word, encabezado en <b> y no en <strong>
    html_b = """<div class="descripcion-contenido">
    <P class=MsoNormal align=center><B>DECRETA:</B></P>
    <P class=MsoNormal><B>ARTÍCULO 1º.-</B>&nbsp;Adiciónase el artículo 250 del Código Civil con el siguiente inciso:</P>
    <P class=MsoNormal>Los hijos son legítimos, extramatrimoniales y adoptivos y tendrán iguales derechos.</P>
    <P class=MsoNormal><B>ARTÍCULO&nbsp;<A id=sp9 name=9>&nbsp;</A>9º.-</B>&nbsp;El artículo 1240 del Código Civil quedará así:</P>
    <p class=MsoNormal><b>ARTÍCULO
    2º.</b>En todos los casos en que la ley señale los 21 años.</p>
    </div>"""
    arts = funcionpublica.procesar(html_b)
    assert [a.numero for a in arts] == ["1", "9", "2"]
    assert arts[0].parrafos == ["Adiciónase el artículo 250 del Código Civil con el siguiente inciso:",
                                "Los hijos son legítimos, extramatrimoniales y adoptivos y tendrán iguales derechos."]
    assert arts[2].texto == "En todos los casos en que la ley señale los 21 años."

    # Ley 153 de 1887: encabezado sin negrilla; notas de vigencia al comienzo del texto
    html_texto = """<div class="descripcion-contenido">
    <p align="center"><strong>REGLAS GENERALES SOBRE VALIDEZ Y APLICACIÓN DE LAS LEYES</strong></p>
    <p>ARTÍCULO <a id="sp1" name="1"></a> 1. Siempre que se advierta incongruencia en las leyes.</p>
    <p>ARTÍCULO <a id="sp3" name="3"></a> 3.Estímase insubsistente una disposición legal.</p>
    <p>ARTÍCULO 6. <strong>Derogado por el Art. 40, Acto legislativo 3 de 1910</strong>. Una disposición expresa.</p>
    <p>ARTÍCULO 10. <strong>Artículo subrogado por el artículo 4. de la Ley 169 de 1889</strong>: Tres decisiones.</p>
    </div>"""
    arts = funcionpublica.procesar(html_texto)
    assert [a.numero for a in arts] == ["1", "3", "6", "10"]
    assert arts[1].texto == "Estímase insubsistente una disposición legal."
    assert arts[1].ruta == ["REGLAS GENERALES SOBRE VALIDEZ Y APLICACIÓN DE LAS LEYES"]
    assert [a.estado for a in arts] == ["vigente", "vigente", "derogado", "modificado"]


def test_senado_ley_aprobatoria_de_tratado():
    from paracite.ingest.fuentes import senado

    # Ley 2273 de 2022: primero se transcribe el Acuerdo de Escazú (arts. 1 a 26) y después de
    # «DECRETA:» vienen los artículos de la ley, que son los que se citan como «Ley 2273 de 2022».
    html = """<body>
    <p><a class="bookmarkaj" name="1">ART&Iacute;CULO 1. </A></p>
    <p class="centrado"><span class="b_aj">Objetivo</span></p>
    <p>El objetivo del presente Acuerdo es garantizar la implementación plena.</p>
    <p><a class="bookmarkaj" name="2">ART&Iacute;CULO 2. </A></p>
    <p>Definiciones del Acuerdo.</p>
    <p class="centrado">DECRETA: </p>
    <p><a class="bookmarkaj" name="1B">ART&Iacute;CULO 1o.</A> Apru&eacute;bese el &#8220;Acuerdo regional&#8221;.</p>
    <p><a class="bookmarkaj" name="2B">ART&Iacute;CULO 2o.</A> De conformidad con la Ley 7 de 1994.</p>
    <p><a class="bookmarkaj" name="3B">ART&Iacute;CULO 3o.</A> La presente ley rige a partir de su publicación.</p>
    </body>"""
    arts = senado.procesar(html)
    assert [a.numero for a in arts] == ["1", "2", "3"]
    assert arts[0].texto == "Apruébese el “Acuerdo regional”."
    assert arts[2].texto == "La presente ley rige a partir de su publicación."
