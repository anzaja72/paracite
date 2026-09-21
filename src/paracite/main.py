from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from paracite.api.routes.cite import router as cite_router
from paracite.api.routes.corpus import router as corpus_router
from paracite.api.routes.health import health_router, ingest_router, me_router
from paracite.auth.keys import resolve_key, seed_demo_key
from paracite.auth.rate_limit import RateLimiter
from paracite.config import Settings, get_settings
from paracite.db.models import make_engine, make_session_factory, Base
from paracite.services.cite import CiteService
from paracite.services.ingest import IngestService
from paracite.wiring import build_classifier, build_retriever

STATIC_DIR = Path(__file__).resolve().parent / "static"
OPEN_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="ParaCite API",
        version=settings.version,
        description=(
            "Citas jurídicas de precisión para agentes Legal-AI. "
            "Solo se devuelven matches con `es_cita_valida_alta_precision` "
            "por encima del umbral (default 0.87). El corpus seed está etiquetado [FIXTURE]."
        ),
        contact={"name": "ParaCite"},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)
    retriever, local_store = build_retriever(settings)
    classifier = build_classifier(settings)
    rate_limiter = RateLimiter(settings.redis_url)

    redis_client = rate_limiter._redis
    with SessionLocal() as db:
        seed_demo_key(db, settings.demo_api_key, settings.rate_limit_per_minute)

    app.state.settings = settings
    app.state.SessionLocal = SessionLocal
    app.state.retriever = retriever
    app.state.local_store = local_store
    app.state.classifier = classifier
    app.state.rate_limiter = rate_limiter
    app.state.cite_service = CiteService(retriever, classifier, retrieval_top_k=settings.retrieval_top_k)
    app.state.ingest_service = IngestService(redis_client)

    @app.middleware("http")
    async def auth_and_limit(request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or path in OPEN_PATHS
            or path.startswith("/static")
            or path.startswith("/corpus")
            or path == "/"
        ):
            return await call_next(request)
        header = request.headers.get("authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return JSONResponse({"detail": "API key requerida (Authorization: Bearer)"}, status_code=401)
        db = SessionLocal()
        try:
            principal = resolve_key(db, token.strip())
        finally:
            db.close()
        if principal is None:
            return JSONResponse({"detail": "API key inválida"}, status_code=401)
        allowed, remaining = rate_limiter.hit(
            str(principal.key.id), principal.key.rate_limit_per_minute
        )
        if not allowed:
            return JSONResponse(
                {"detail": "Rate limit excedido", "code": "RATE_LIMITED"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        request.state.principal = principal
        request.state.rate_remaining = remaining
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(principal.key.rate_limit_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(cite_router)
    app.include_router(ingest_router)
    app.include_router(corpus_router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("paracite.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
