from fastapi import APIRouter, HTTPException, Request, status

from paracite.api.schemas import CiteRequest, CiteResponse, RevisarRequest, RevisarResponse
from paracite.auth.keys import Principal

router = APIRouter(prefix="/v1", tags=["cite"])


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key requerida")
    return principal


@router.post("/cite", response_model=CiteResponse)
def cite(payload: CiteRequest, request: Request) -> CiteResponse:
    principal = _principal(request)
    db = request.app.state.SessionLocal()
    try:
        return request.app.state.cite_service.cite(payload, db=db, api_key_id=principal.key.id)
    finally:
        db.close()


@router.post("/revisar", response_model=RevisarResponse)
def revisar(payload: RevisarRequest, request: Request) -> RevisarResponse:
    """Compara un documento generado con el corpus y devuelve JSON, sin reescribirlo."""
    principal = _principal(request)
    db = request.app.state.SessionLocal()
    try:
        return request.app.state.revisar_service.revisar(
            payload, db=db, api_key_id=principal.key.id
        )
    finally:
        db.close()
