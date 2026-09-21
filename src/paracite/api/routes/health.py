from fastapi import APIRouter, HTTPException, Request, status

from paracite.api.schemas import IngestAccepted, IngestDisabled, IngestRequest, MeResponse, RateLimitInfo
from paracite.services.cite import usage_counts

me_router = APIRouter(prefix="/v1", tags=["account"])
ingest_router = APIRouter(prefix="/v1", tags=["ingest"])
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health(request: Request):
    settings = request.app.state.settings
    retriever = request.app.state.retriever
    classifier = request.app.state.classifier
    checks = {
        "retrieval": getattr(retriever, "name", "unknown"),
        "classifier": getattr(classifier, "name", "unknown"),
        "postgres": "sqlite" if settings.database_url.startswith("sqlite") else "postgres",
        "redis": request.app.state.rate_limiter.backend,
        "ingest": "enabled" if settings.enable_ingest else "stub",
    }
    return {
        "status": "ok",
        "service": "paracite",
        "version": settings.version,
        "checks": checks,
    }


@me_router.get("/me", response_model=MeResponse)
def me(request: Request) -> MeResponse:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key requerida")
    remaining = int(getattr(request.state, "rate_remaining", 0))
    db = request.app.state.SessionLocal()
    try:
        uso = usage_counts(db, principal.key.id)
    finally:
        db.close()
    return MeResponse(
        key_id=str(principal.key.id),
        nombre=principal.user.nombre,
        plan=principal.user.plan,
        rate_limit=RateLimitInfo(
            limit=principal.key.rate_limit_per_minute,
            remaining=remaining,
        ),
        uso=uso,
    )


@ingest_router.post("/ingest", response_model=IngestAccepted, status_code=202)
def ingest(payload: IngestRequest, request: Request):
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key requerida")
    settings = request.app.state.settings
    if not settings.enable_ingest:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=IngestDisabled(
                detail=(
                    "La ingesta de corpus es un stub Enterprise en el MVP. "
                    "Active ENABLE_INGEST=true para encolar documentos."
                )
            ).model_dump(),
        )
    db = request.app.state.SessionLocal()
    try:
        return request.app.state.ingest_service.enqueue(payload, db)
    finally:
        db.close()
