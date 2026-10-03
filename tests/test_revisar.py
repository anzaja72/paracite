from tests.conftest import AUTH

SABATICO = "El trabajador tiene derecho a un año sabático retribuido obligatorio cada tres años"
DESPIDO = "El despido disciplinario exige un incumplimiento grave y culpable del trabajador"
CORPUS_KEYS = ("parrafo_exacto", "cita_formal", "enlace_profundo", "chunk_id")


def _revisar(client, **body):
    return client.post("/v1/revisar", json=body, headers=AUTH)


def _core(cita_formal: str) -> str:
    text = cita_formal.removeprefix("[FIXTURE] ").removeprefix("[WEKNORA] ")
    note = text.find(" (")
    if note != -1:
        text = text[:note]
    return text.strip()


def _body(parrafo: str) -> str:
    return parrafo.removeprefix("FIXTURE. ").strip()


def test_revisar_requires_auth(client):
    response = client.post("/v1/revisar", json={"texto": "hola"})
    assert response.status_code == 401


def test_revisar_requires_text_or_spans(client):
    response = _revisar(client)
    assert response.status_code == 422


def test_dejar_cuando_la_cita_ya_esta_completa(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    texto = f"{_core(chunk.cita_formal)}. {_body(chunk.parrafo)}"
    response = _revisar(client, afirmaciones=[{"id": "jornada", "texto": texto}])
    assert response.status_code == 200, response.text
    data = response.json()
    assert "texto_revisado" not in data
    assert "documento" not in data
    item = data["resultados"][0]
    assert item["id"] == "jornada"
    assert item["estado"] == "dejar"
    assert item["texto"] == texto
    assert "Déjala como está" in item["indicacion"]
    for key in CORPUS_KEYS:
        assert key not in item


def test_completar_por_cita_de_articulo_sin_transcripcion(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    texto = "Véase el Estatuto de los Trabajadores, art. 34.1."
    response = _revisar(client, afirmaciones=[{"texto": texto}])
    assert response.status_code == 200, response.text
    item = response.json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == chunk.id
    assert item["cita_formal"] == chunk.cita_formal
    assert item["parrafo_exacto"] == chunk.parrafo
    assert item["enlace_profundo"] == chunk.enlace_profundo
    assert item["parrafo_exacto"] not in texto
    assert "incompleta o no es exacta" in item["indicacion"]


def test_completar_si_el_parrafo_esta_pero_la_cita_no(client, app):
    chunk = app.state.local_store.get("fix-et-038-vacaciones")
    texto = _body(chunk.parrafo)
    item = _revisar(client, afirmaciones=[{"texto": texto}]).json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == chunk.id
    assert item["cita_formal"] == chunk.cita_formal
    assert item["parrafo_exacto"] == chunk.parrafo
    assert item["enlace_profundo"] == chunk.enlace_profundo


def test_completar_con_cita_en_campo_aparte(client, app):
    chunk = app.state.local_store.get("fix-et-038-vacaciones")
    response = _revisar(
        client,
        afirmaciones=[
            {
                "id": "vac",
                "texto": "Las vacaciones se pactan en convenio.",
                "cita": _core(chunk.cita_formal),
            }
        ],
    )
    item = response.json()["resultados"][0]
    assert item["id"] == "vac"
    assert item["estado"] == "completar"
    assert item["chunk_id"] == chunk.id
    assert item["cita_formal"] == chunk.cita_formal
    assert _core(chunk.cita_formal) in item["texto"]


def test_tema_coincidente_sin_cita_exacta_es_completar(client, app):
    chunk = app.state.local_store.get("fix-et-054-despido-disciplinario")
    item = _revisar(client, afirmaciones=[{"texto": DESPIDO}]).json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == chunk.id
    assert item["parrafo_exacto"] == chunk.parrafo
    assert item["cita_formal"].startswith("[FIXTURE]")


def test_tesis_libre_sin_norma_es_no_sostiene(client):
    item = _revisar(client, afirmaciones=[{"texto": SABATICO}]).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    assert "supera el umbral" in item["indicacion"]
    for key in CORPUS_KEYS:
        assert key not in item
    assert "[FIXTURE]" not in item["indicacion"]
    assert "Estatuto" not in item["indicacion"]


def test_umbral_alto_no_adivina_la_norma(client):
    item = _revisar(
        client,
        umbral_confianza=0.98,
        afirmaciones=[{"texto": DESPIDO}],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    for key in CORPUS_KEYS:
        assert key not in item


def test_jurisdiccion_co_no_trata_el_seed_como_ley_colombiana(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    texto = f"{_core(chunk.cita_formal)}. {_body(chunk.parrafo)}"
    data = _revisar(
        client,
        jurisdiccion="co",
        afirmaciones=[{"texto": texto}],
    ).json()
    assert data["jurisdiccion"] == "CO"
    item = data["resultados"][0]
    assert item["estado"] == "no_sostiene"
    for key in CORPUS_KEYS:
        assert key not in item


def test_sin_jurisdiccion_revisa_los_chunks_cargados(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    data = _revisar(client, afirmaciones=[{"texto": _core(chunk.cita_formal)}]).json()
    assert data["jurisdiccion"] is None
    assert data["resultados"][0]["estado"] == "completar"
    assert data["resultados"][0]["chunk_id"] == chunk.id


def test_un_resultado_por_afirmacion_y_el_texto_no_se_reescribe(client, app):
    chunk = app.state.local_store.get("fix-et-034-jornada")
    completa = f"{_core(chunk.cita_formal)}. {_body(chunk.parrafo)}"
    parcial = _core(chunk.cita_formal)
    response = _revisar(
        client,
        afirmaciones=[
            {"id": "ok", "texto": completa},
            {"id": "parcial", "texto": parcial},
            {"id": "libre", "texto": SABATICO},
        ],
    )
    assert response.status_code == 200, response.text
    items = response.json()["resultados"]
    assert [item["id"] for item in items] == ["ok", "parcial", "libre"]
    assert [item["estado"] for item in items] == ["dejar", "completar", "no_sostiene"]
    assert items[0]["texto"] == completa
    assert items[1]["texto"] == parcial
    assert items[2]["texto"] == SABATICO
    assert "parrafo_exacto" not in items[0]
    assert items[1]["parrafo_exacto"] == chunk.parrafo
    assert "parrafo_exacto" not in items[2]


def test_texto_plano_se_parte_por_parrafos(client):
    texto = (
        "Véase el Estatuto de los Trabajadores, art. 34.1.\n\n"
        f"{SABATICO}"
    )
    items = _revisar(client, texto=texto).json()["resultados"]
    assert [item["estado"] for item in items] == ["completar", "no_sostiene"]
    assert items[0]["id"] == "a1"
    assert items[1]["id"] == "a2"
