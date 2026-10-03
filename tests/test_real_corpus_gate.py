from paracite.api.schemas import CiteRequest, JevClassification, TipoCoincidencia
from paracite.classifier.mock import MockPrecisionClassifier
from paracite.retrieval.local_store import LocalBm25Store
from paracite.retrieval.protocol import Chunk
from paracite.services.cite import CiteService
from tests.conftest import AUTH

TESIS = (
    "El ejemplo de prueba reconoce un plazo de noventa días hábiles "
    "para contestar la demanda de demostración"
)
PARRAFO = (
    "El ejemplo de prueba reconoce un plazo de noventa días hábiles "
    "para contestar la demanda de demostración en este chunk sintético."
)
CITA = "Ley 0000 de 2099, art. 7"


class _AlwaysValid:
    name = "stub"

    def classify(self, tesis, chunks):
        return [
            JevClassification(
                chunk_id=chunk.id,
                relevancia_semantica=0.95,
                es_cita_valida_alta_precision=True,
                tipo_coincidencia=TipoCoincidencia.fundamento_directo,
            )
            for chunk in chunks
        ]


class _FixedRetriever:
    """Devuelve el chunk aunque BM25 anule el idf de un corpus de un solo documento."""

    name = "fixed"

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks

    def retrieve(self, tesis: str, **kwargs) -> list[Chunk]:
        return list(self._chunks)

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def get(self, chunk_id: str) -> Chunk | None:
        for chunk in self._chunks:
            if chunk.id == chunk_id:
                return chunk
        return None


def _chunk() -> Chunk:
    return Chunk(
        id="test-co-ley-0000-art-7",
        tipo="norma",
        jurisdiccion="CO",
        materia="prueba",
        cita_formal=CITA,
        titulo="Chunk sintético, no es corpus oficial",
        parrafo=PARRAFO,
        enlace_profundo="https://example.test/co/ley-0000/art-7",
        metadatos={
            "etiqueta_fixture": False,
            "norma": "LEY-0000",
            "articulo": "7",
            "holds": ["noventa días hábiles", "contestar la demanda"],
        },
        texto_completo=PARRAFO,
    )


def _install(app, chunk: Chunk) -> LocalBm25Store:
    store = LocalBm25Store([*app.state.local_store.all_chunks(), chunk])
    app.state.cite_service.retriever = store
    app.state.revisar_service.retriever = store
    return store


def test_mock_no_descarta_cita_real():
    found = MockPrecisionClassifier().classify(TESIS, [_chunk()])
    assert found[0].es_cita_valida_alta_precision is True
    assert found[0].tipo_coincidencia == TipoCoincidencia.fundamento_directo


def test_cite_service_publica_chunk_sin_prefijo_fixture():
    chunk = _chunk()
    response = CiteService(_FixedRetriever([chunk]), _AlwaysValid()).cite(
        CiteRequest(tesis=TESIS, jurisdiccion="CO")
    )
    assert response.sin_match_alta_confianza is False
    assert len(response.matches) == 1
    assert response.matches[0].id == chunk.id
    assert response.matches[0].cita_formal == CITA
    assert not response.matches[0].cita_formal.startswith("[FIXTURE]")
    assert not response.matches[0].cita_formal.startswith("[WEKNORA]")


def test_cite_service_no_inventa_cita_vacia():
    chunk = _chunk()
    chunk.cita_formal = "   "
    response = CiteService(_FixedRetriever([chunk]), _AlwaysValid()).cite(
        CiteRequest(tesis=TESIS, jurisdiccion="CO")
    )
    assert response.matches == []
    assert response.sin_match_alta_confianza is True


def test_http_cite_no_descarta_chunk_fuera_de_fixture(app, client):
    chunk = _chunk()
    _install(app, chunk)
    response = client.post(
        "/v1/cite",
        json={"tesis": TESIS, "jurisdiccion": "CO"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sin_match_alta_confianza"] is False
    match = data["matches"][0]
    assert match["id"] == chunk.id
    assert match["cita_formal"] == CITA
    assert match["parrafo_exacto"] == PARRAFO
    assert match["enlace_profundo"] == chunk.enlace_profundo
    assert match["metadatos"]["jurisdiccion"] == "CO"
    assert not match["cita_formal"].startswith("[FIXTURE]")


def test_revisar_chunk_no_fixture_dejar_y_completar(app, client):
    chunk = _chunk()
    _install(app, chunk)
    completa = f"{CITA}. {PARRAFO}"
    response = client.post(
        "/v1/revisar",
        json={
            "jurisdiccion": "CO",
            "afirmaciones": [
                {"id": "lista", "texto": completa},
                {"id": "corta", "texto": "Según la Ley 0000 de 2099, art. 7, hay un plazo."},
            ],
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    lista, corta = response.json()["resultados"]
    assert lista["estado"] == "dejar"
    assert "parrafo_exacto" not in lista
    assert "cita_formal" not in lista
    assert corta["estado"] == "completar"
    assert corta["cita_formal"] == CITA
    assert corta["parrafo_exacto"] == PARRAFO
    assert corta["enlace_profundo"] == chunk.enlace_profundo
    assert not corta["cita_formal"].startswith("[FIXTURE]")


def test_sin_jurisdiccion_el_chunk_co_sigue_siendo_visible(app, client):
    chunk = _chunk()
    _install(app, chunk)
    response = client.post(
        "/v1/revisar",
        json={"afirmaciones": [{"texto": f"{CITA}. {PARRAFO}"}]},
        headers=AUTH,
    )
    item = response.json()["resultados"][0]
    assert response.json()["jurisdiccion"] is None
    assert item["estado"] == "dejar"


def test_filtro_es_no_confunde_el_chunk_co_con_el_seed(app, client):
    _install(app, _chunk())
    response = client.post(
        "/v1/revisar",
        json={
            "jurisdiccion": "ES",
            "afirmaciones": [{"texto": f"{CITA}. {PARRAFO}"}],
        },
        headers=AUTH,
    )
    item = response.json()["resultados"][0]
    assert item["estado"] == "no_sostiene"
    assert "cita_formal" not in item
    assert "parrafo_exacto" not in item
