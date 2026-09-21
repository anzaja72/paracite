from tests.conftest import AUTH

POSITIVE = [
    (
        "El despido disciplinario exige un incumplimiento grave y culpable del trabajador",
        "fix-et-054-despido-disciplinario",
    ),
    (
        "Las vacaciones anuales retribuidas son de treinta días naturales",
        "fix-et-038-vacaciones",
    ),
    (
        "La jornada máxima ordinaria de trabajo es de cuarenta horas semanales de trabajo efectivo",
        "fix-et-034-jornada",
    ),
    (
        "El periodo de prueba debe constar por escrito según los convenios colectivos",
        "fix-et-014-periodo-prueba",
    ),
    (
        "La indemnización por despido improcedente es de treinta y tres días de salario por año de servicio",
        "fix-et-056-improcedente",
    ),
    (
        "El trabajador puede solicitar reducción de jornada por guarda legal de un menor",
        "fix-et-037-guarda-legal",
    ),
    (
        "El empresario deberá garantizar la seguridad y salud de los trabajadores y la prevención de los riesgos",
        "fix-lprl-014-seguridad",
    ),
    (
        "Quien por acción u omisión causa daño a otro, interviniendo culpa o negligencia, está obligado a reparar el daño",
        "fix-cc-1902-aquiliana",
    ),
    (
        "Los contratos se perfeccionan por el consentimiento y obligan conforme a la buena fe",
        "fix-cc-1258-consentimiento",
    ),
    (
        "Las acciones personales prescriben a los cinco años desde que pueda exigirse el cumplimiento",
        "fix-cc-1964-prescripcion",
    ),
    (
        "Los derechos deberán ejercitarse conforme a la buena fe y la ley no ampara el abuso del derecho",
        "fix-cc-007-buena-fe",
    ),
    (
        "Por el contrato de compraventa uno se obliga a entregar una cosa determinada y el otro un precio cierto",
        "fix-cc-1445-compraventa",
    ),
    (
        "El despido nulo se produce por discriminación o violación de derechos fundamentales",
        "fix-et-055-nulo",
    ),
    (
        "La prestación de horas extraordinarias será voluntaria salvo pacto en convenio colectivo",
        "fix-et-035-horas-extra",
    ),
    (
        "El pago del salario se hace en la fecha convenida y no puede ser inferior al salario mínimo",
        "fix-et-029-salario",
    ),
    (
        "El contrato de duración determinada solo cabe por circunstancias de la producción; si no, se presume indefinido",
        "fix-et-015-temporal",
    ),
    (
        "Quedan sujetos a daños y perjuicios quienes incumplan con dolo, negligencia o morosidad",
        "fix-cc-1101-incumplimiento",
    ),
    (
        "La propiedad es el derecho de gozar y disponer de una cosa, con acción para reivindicarla",
        "fix-cc-348-propiedad",
    ),
    (
        "La carta de despido debe fijar los hechos que lo motivan para que el trabajador pueda impugnarlos",
        "fix-doctrina-despido-carta",
    ),
    (
        "La responsabilidad del 1902 exige nexo causal y causa adecuada entre la conducta y el daño",
        "fix-doctrina-nexo-causal",
    ),
]

NEGATIVE = [
    "El trabajador tiene derecho a un año sabático retribuido obligatorio cada tres años",
    "El Tribunal Supremo ha establecido que los gatos tienen personalidad jurídica plena en España",
    "Toda compraventa verbal de inmuebles es válida sin excepción en España",
    "La prescripción de las acciones personales es de cincuenta años",
    "El despido disciplinario no requiere incumplimiento alguno",
    "Las horas extraordinarias son siempre obligatorias y sin límite anual",
    "Las vacaciones anuales son de quince días y sustituibles por dinero",
]


def _cite(client, tesis, **extra):
    body = {"tesis": tesis, **extra}
    return client.post("/v1/cite", json=body, headers=AUTH)


def test_at_least_twenty_fixture_theses():
    assert len(POSITIVE) + len(NEGATIVE) >= 20


def test_positive_theses_return_labeled_fixture(client):
    for tesis, chunk_id in POSITIVE:
        response = _cite(client, tesis)
        assert response.status_code == 200, tesis
        data = response.json()
        assert data["sin_match_alta_confianza"] is False, tesis
        ids = [m["id"] for m in data["matches"]]
        assert chunk_id in ids, (tesis, ids)
        for match in data["matches"]:
            assert match["confianza"] >= 0.87
            assert match["cita_formal"].startswith("[FIXTURE]")
            assert match["parrafo_exacto"]
            assert match["enlace_profundo"]
            assert match["metadatos"]["es_cita_valida_alta_precision"] is True


def test_negative_theses_do_not_hallucinate(client):
    for tesis in NEGATIVE:
        data = _cite(client, tesis).json()
        assert data["matches"] == [], tesis
        assert data["sin_match_alta_confianza"] is True, tesis


def test_default_jurisdiccion_es(client):
    data = _cite(client, POSITIVE[0][0]).json()
    assert data["matches"][0]["metadatos"]["jurisdiccion"] == "ES"


def test_other_jurisdiction_has_no_corpus(client):
    data = _cite(client, POSITIVE[0][0], jurisdiccion="MX").json()
    assert data["sin_match_alta_confianza"] is True
    assert data["matches"] == []


def test_max_resultados_one(client):
    data = _cite(client, POSITIVE[0][0], max_resultados=1).json()
    assert len(data["matches"]) == 1


def test_umbral_too_high_returns_empty(client):
    data = _cite(client, POSITIVE[0][0], umbral_confianza=0.99).json()
    assert data["matches"] == []
    assert data["sin_match_alta_confianza"] is True


def test_empty_tesis_422(client):
    response = _cite(client, "   ")
    assert response.status_code == 422


def test_latency_under_budget_with_mocks(client):
    data = _cite(client, POSITIVE[0][0]).json()
    assert data["tiempo_procesamiento_ms"] < 800


def test_incluir_texto_completo(client):
    data = _cite(client, POSITIVE[0][0], incluir_texto_completo=True).json()
    assert "texto_completo" in data["matches"][0]["metadatos"]


def test_no_unlabeled_citations_in_seed(client):
    data = _cite(client, POSITIVE[7][0]).json()
    for match in data["matches"]:
        assert "[FIXTURE]" in match["cita_formal"]
        assert "STS" not in match["cita_formal"]
        assert "ECLI" not in match["cita_formal"]
