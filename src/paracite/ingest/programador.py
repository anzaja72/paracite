"""Carga continua del corpus dentro del proceso de la API.

Si PARACITE_INGEST_INTERVAL_HOURS > 0, una tarea en segundo plano ejecuta el cargador cada N horas
(la primera vez, a los PARACITE_INGEST_FIRST_DELAY_S segundos de arrancar). Si el corpus cambió,
reconstruye el índice y lo reemplaza en caliente: no hay que reiniciar el servicio.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI

from paracite.ingest import cargar

log = logging.getLogger("paracite.ingest")


def _huella_corpus(corpus_dir: Path) -> tuple:
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in (corpus_dir / "co").glob("*.jsonl")))


def recargar_indice(app: FastAPI) -> None:
    from paracite.wiring import build_retriever

    retriever, local = build_retriever(app.state.settings)
    app.state.retriever = retriever
    app.state.local_store = local
    app.state.cite_service.retriever = retriever
    log.info("Índice del corpus recargado: %d fragmentos", len(local.all_chunks()))


async def ciclo(app: FastAPI, *, cada_horas: float, primera_espera_s: float) -> None:
    corpus_dir = Path(app.state.settings.corpus_dir)
    await asyncio.sleep(primera_espera_s)
    while True:
        antes = _huella_corpus(corpus_dir)
        try:
            codigo = await asyncio.to_thread(cargar.main, ["--salida", str(corpus_dir / "co"),
                                                           "--catalogo", str(corpus_dir / "co" / "catalogo.yaml")])
            if codigo:
                log.warning("Carga del corpus terminó con errores (código %s); ver manifiesto.json", codigo)
        except Exception:
            log.exception("Fallo en la carga programada del corpus")
        if _huella_corpus(corpus_dir) != antes:
            await asyncio.to_thread(recargar_indice, app)
        await asyncio.sleep(cada_horas * 3600)
