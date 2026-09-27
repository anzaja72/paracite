from fastapi import APIRouter, HTTPException, Request, status

from paracite.retrieval.protocol import Chunk

router = APIRouter(tags=["corpus"])


def _es_oficial(chunk: Chunk) -> bool:
    return bool(chunk.metadatos.get("fuente_oficial"))


def _vista(chunk: Chunk) -> dict:
    oficial = _es_oficial(chunk)
    m = chunk.metadatos
    vista = {
        "id": chunk.id,
        "tipo": chunk.tipo,
        "jurisdiccion": chunk.jurisdiccion,
        "materia": chunk.materia,
        "cita_formal": chunk.cita_formal,
        "titulo": chunk.titulo,
        "parrafo": chunk.parrafo,
        "etiqueta_fixture": not oficial,
    }
    if oficial:
        vista.update({
            "norma": m.get("norma"),
            "articulo": m.get("articulo"),
            "estado": m.get("estado"),
            "notas_vigencia": m.get("notas_vigencia", []),
            "ruta": m.get("ruta", []),
            "url_oficial": chunk.enlace_profundo,
            "capturado_en": m.get("capturado_en"),
            "aviso": "Texto tomado de la fuente oficial indicada; verifique la vigencia en la fuente.",
        })
    else:
        vista["aviso"] = "Documento de demostración. No es una cita judicial verificada."
    return vista


@router.get("/corpus/{chunk_id}")
def get_chunk(chunk_id: str, request: Request):
    chunk: Chunk | None = request.app.state.local_store.get(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk no encontrado")
    return _vista(chunk)


@router.get("/v1/norma/{norma}/{articulo}", tags=["corpus"])
def get_articulo(norma: str, articulo: str, request: Request, jurisdiccion: str = "CO"):
    """¿Existe este artículo en el corpus oficial? Devuelve su texto, estado y enlace oficial."""
    store = request.app.state.local_store
    chunk = store.buscar_articulo(jurisdiccion.upper(), norma, articulo)
    if chunk is None:
        normas = {str(c.metadatos.get("norma", "")).upper() for c in store.all_chunks()
                  if c.jurisdiccion == jurisdiccion.upper() and c.metadatos.get("fuente_oficial")}
        cubierta = norma.upper() in normas
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "existe": False,
                "norma_cubierta": cubierta,
                "mensaje": (f"El artículo {articulo} no existe en {norma.upper()} según el corpus oficial."
                            if cubierta else
                            f"La norma {norma.upper()} aún no está en el corpus: no se puede verificar."),
            },
        )
    return {"existe": True, **_vista(chunk)}
