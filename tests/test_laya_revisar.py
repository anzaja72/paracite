"""Laya es opcional. Estos tests no descargan pesos: el router se simula."""

from paracite.classifier.laya import (
    LAYA_QUESTIONS,
    LayaRouterClient,
    laya_device,
    laya_mode_enabled,
    support_confidence,
)
from paracite.retrieval.protocol import Chunk
from paracite.services.revisar import _ART_RE
from tests.conftest import AUTH

CORPUS_KEYS = ("parrafo_exacto", "cita_formal", "enlace_profundo", "chunk_id")
TESIS_CST = "El salario debe pagarse en la forma y periodos pactados con el trabajador"
CST_ID = "co-cst-art-134"


class ScriptedLaya:
    """El mock dice si un chunk ya recuperado apoya la tesis. No redacta texto."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.seen: list[list[str]] = []

    def score(self, tesis: str, chunks: list) -> list[tuple[str, float]]:
        self.seen.append([chunk.id for chunk in chunks])
        return [(chunk.id, float(self.scores.get(chunk.id, 0.0))) for chunk in chunks]


class _Router:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple] = []

    def predict(self, state, questions, model=None, **kwargs):
        self.calls.append((state, questions, model))
        return self.payload


def _revisar(client, **body):
    return client.post("/v1/revisar", json=body, headers=AUTH)


def test_el_paquete_laya_no_se_carga_en_los_tests(app):
    assert laya_mode_enabled("off") is False
    assert app.state.revisar_service.laya is None


def test_preguntas_laya_solo_noul_y_choice():
    types = {question["type"] for question in LAYA_QUESTIONS.values()}
    assert types == {"noul", "choice"}
    for question in LAYA_QUESTIONS.values():
        assert "generate" not in question
        assert "instructions" in question


def test_dispositivo_mps_o_cpu():
    class _Mps:
        def is_available(self):
            return True

    class _Torch:
        class backends:
            mps = _Mps()

    assert laya_device(_Torch()) == "mps"

    class _Cpu:
        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

    assert laya_device(_Cpu()) == "cpu"
    assert laya_device(object()) == "cpu"


def test_router_solo_publica_si_choice_apoya_y_noul_es_alto():
    router = _Router(
        {
            "answers": {
                "supports": {"noul": 0.94},
                "relation": {"choice": "supports", "confidence": 0.91},
            }
        }
    )
    chunk = Chunk(
        id="co-cp-art-29",
        tipo="constitucion",
        jurisdiccion="CO",
        materia="constitucional",
        cita_formal="Constitución Política, art. 29",
        titulo="Constitución Política, art. 29",
        parrafo="El debido proceso se aplicará a toda clase de actuaciones judiciales.",
        enlace_profundo="https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=4125#29",
    )
    vacio = Chunk(
        id="co-cc-art-10",
        tipo="codigo",
        jurisdiccion="CO",
        materia="civil",
        cita_formal="Código Civil, art. 10",
        titulo="Código Civil, art. 10",
        parrafo="",
        enlace_profundo="https://example.test/vacio",
    )
    client = LayaRouterClient(router)
    scored = dict(client.score("hay debido proceso", [vacio, chunk]))
    assert "co-cc-art-10" not in scored
    assert scored["co-cp-art-29"] == 0.94
    state, questions, model = router.calls[0]
    assert model == "multilingual"
    assert state["parrafo"] == chunk.parrafo
    assert {item["type"] for item in questions.values()} == {"noul", "choice"}
    router.payload = {
        "answers": {
            "supports": {"noul": 0.96},
            "relation": {"choice": "contradicts"},
        }
    }
    assert support_confidence(router.payload) == 0.0


def test_laya_completa_tesis_sin_numero_de_articulo(app, client):
    chunk = app.state.local_store.get(CST_ID)
    assert chunk is not None
    assert chunk.id.startswith("co-cst-")
    assert chunk.parrafo.strip()
    assert not chunk.cita_formal.startswith("[FIXTURE]")
    assert _ART_RE.search(TESIS_CST) is None
    laya = ScriptedLaya({chunk.id: 0.94})
    app.state.revisar_service.laya = laya
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"id": "salario", "texto": TESIS_CST}],
    ).json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == chunk.id
    assert item["cita_formal"] == chunk.cita_formal
    assert item["parrafo_exacto"] == chunk.parrafo
    assert item["enlace_profundo"] == chunk.enlace_profundo
    assert item["parrafo_exacto"] not in item["texto"]
    assert laya.seen and chunk.id in laya.seen[0]
    for chunk_id in laya.seen[0]:
        seen = app.state.local_store.get(chunk_id)
        assert seen is not None
        assert seen.jurisdiccion == "CO"
        assert seen.parrafo.strip()
        assert not seen.cita_formal.startswith("[FIXTURE]")


def test_laya_sin_apoyo_es_no_sostiene(app, client):
    laya = ScriptedLaya({})
    app.state.revisar_service.laya = laya
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"texto": TESIS_CST}],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    assert laya.seen
    for key in CORPUS_KEYS:
        assert key not in item
    assert "[FIXTURE]" not in item["indicacion"]


def test_laya_no_devuelve_fixture_espanola_si_la_jurisdiccion_es_co(app, client):
    laya = ScriptedLaya({"fix-et-054-despido-disciplinario": 0.99})
    app.state.revisar_service.laya = laya
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[
            {
                "texto": (
                    "El despido disciplinario exige un incumplimiento grave "
                    "y culpable del trabajador"
                )
            }
        ],
    ).json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    for key in CORPUS_KEYS:
        assert key not in item
    seen = {chunk_id for batch in laya.seen for chunk_id in batch}
    assert "fix-et-054-despido-disciplinario" not in seen


def test_el_articulo_exacto_no_consulta_laya(app, client):
    laya = ScriptedLaya({})
    app.state.revisar_service.laya = laya
    item = _revisar(
        client,
        jurisdiccion="CO",
        afirmaciones=[{"texto": "Constitución art. 29"}],
    ).json()["resultados"][0]
    assert item["estado"] == "completar"
    assert item["chunk_id"] == "co-cp-art-29"
    assert item["cita_formal"].startswith("Constitución")
    assert "debido proceso" in item["parrafo_exacto"].lower()
    assert laya.seen == []
