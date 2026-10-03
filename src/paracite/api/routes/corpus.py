from fastapi import APIRouter, HTTPException, Request, status

from paracite.retrieval.protocol import Chunk

router = APIRouter(tags=["corpus"])


@router.get("/corpus/{chunk_id}")
def get_chunk(chunk_id: str, request: Request):
    chunk: Chunk | None = request.app.state.local_store.get(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk no encontrado")
    es_fixture = bool(chunk.metadatos.get("etiqueta_fixture")) or chunk.cita_formal.startswith(
        "[FIXTURE]"
    )
    payload = {
        "id": chunk.id,
        "tipo": chunk.tipo,
        "jurisdiccion": chunk.jurisdiccion,
        "materia": chunk.materia,
        "cita_formal": chunk.cita_formal,
        "titulo": chunk.titulo,
        "parrafo": chunk.parrafo,
        "etiqueta_fixture": es_fixture,
    }
    if es_fixture:
        payload["aviso"] = "Documento de demostración. No es una cita judicial verificada."
    return payload
