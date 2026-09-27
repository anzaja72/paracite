"""Carga y actualización del corpus colombiano.

Uso:
    uv run python -m paracite.ingest.cargar                       # todas las normas activas del catálogo
    uv run python -m paracite.ingest.cargar --solo CP CST         # algunas
    uv run python -m paracite.ingest.cargar --archivo CP=cp.html  # desde un HTML ya descargado

Salida (por defecto corpus/co/):
    <SIGLA>.jsonl            fragmentos vigentes (un artículo por línea) — lo que carga ParaCite
    manifiesto.json          por norma: huella global, nº de artículos, fecha, url, cambios
    historial/<SIGLA>-<fecha>.jsonl   versión anterior completa cada vez que el texto cambia

Protecciones:
    - Si la fuente falla o devuelve muchos menos artículos que la versión anterior (posible cambio
      de formato o página de error), NO se reemplaza el corpus: se reporta y se sale con código 2.
    - Entre descargas se espera `--pausa` segundos (por defecto 2) para no cargar el portal.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from paracite.ingest.fuentes import funcionpublica
from paracite.ingest.modelo import NormaCatalogo, a_fragmento, huella

log = logging.getLogger("paracite.ingest")

# Misma carpeta que carga la API (PARACITE_CORPUS_DIR, por defecto ./corpus).
SALIDA = Path(os.getenv("PARACITE_CORPUS_DIR", "corpus")) / "co"
CATALOGO = SALIDA / "catalogo.yaml"
USER_AGENT = "ParaCite-Ingest/0.1 (+verificacion de citas juridicas; contacto: legal-ia.co)"
UMBRAL_CAIDA = 0.8  # si hay <80 % de los artículos de la versión anterior, no se reemplaza

PROCESADORES = {"funcionpublica": funcionpublica}


def leer_catalogo(ruta: Path = CATALOGO) -> list[NormaCatalogo]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    normas = []
    for item in datos.get("normas", []):
        item = {**item, "norma_id": str(item["norma_id"]) if item.get("norma_id") else None}
        normas.append(NormaCatalogo(**item))
    return normas


def descargar(url: str, *, timeout: float = 90) -> bytes:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=timeout) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.content


def _leer_jsonl(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def _escribir_jsonl(ruta: Path, filas: list[dict]) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    tmp.replace(ruta)


def cargar_norma(norma: NormaCatalogo, salida: Path, *, html: bytes | None = None) -> dict:
    """Procesa una norma y actualiza su JSONL. Devuelve el resumen para el manifiesto."""
    procesador = PROCESADORES[norma.fuente]
    url = norma.url or ""
    contenido = html if html is not None else descargar(url)
    articulos = procesador.procesar(procesador.decodificar(contenido))
    ahora = datetime.now(UTC).isoformat(timespec="seconds")

    destino = salida / f"{norma.sigla}.jsonl"
    anteriores = _leer_jsonl(destino)
    if anteriores and len(articulos) < UMBRAL_CAIDA * len(anteriores):
        raise RuntimeError(
            f"{norma.sigla}: la fuente devolvió {len(articulos)} artículos y la versión guardada tiene "
            f"{len(anteriores)}. Posible cambio de formato o error del portal; no se reemplaza."
        )

    previas = {f["id"]: f for f in anteriores}
    fragmentos = []
    cambios = {"nuevos": [], "modificados": [], "retirados": []}
    for art in articulos:
        frag = a_fragmento(norma, art, url=url, capturado_en=ahora)
        anterior = previas.get(frag["id"])
        if anterior is None:
            cambios["nuevos"].append(art.numero)
        elif anterior["metadatos"]["huella"] != frag["metadatos"]["huella"]:
            cambios["modificados"].append(art.numero)
        else:
            frag["metadatos"]["capturado_en"] = anterior["metadatos"]["capturado_en"]  # sin cambios
        fragmentos.append(frag)
    ids = {f["id"] for f in fragmentos}
    cambios["retirados"] = [f["metadatos"]["articulo"] for f in anteriores if f["id"] not in ids]

    huella_total = huella("".join(f["metadatos"]["huella"] for f in fragmentos))
    hubo_cambios = any(cambios.values())
    if anteriores and hubo_cambios:
        historial = salida / "historial"
        historial.mkdir(parents=True, exist_ok=True)
        _escribir_jsonl(historial / f"{norma.sigla}-{ahora[:10]}.jsonl", anteriores)
    if hubo_cambios or not destino.exists():
        _escribir_jsonl(destino, fragmentos)

    return {
        "sigla": norma.sigla,
        "nombre": norma.nombre,
        "url": url,
        "articulos": len(fragmentos),
        "estados": _contar(fragmentos),
        "huella": huella_total,
        "actualizado_en": ahora if hubo_cambios else None,
        "verificado_en": ahora,
        "cambios": {k: len(v) for k, v in cambios.items()},
        "detalle_cambios": {k: v[:50] for k, v in cambios.items() if v},
    }


def _contar(fragmentos: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in fragmentos:
        e = f["metadatos"]["estado"]
        out[e] = out.get(e, 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Carga/actualiza el corpus colombiano de ParaCite.")
    ap.add_argument("--catalogo", type=Path, default=CATALOGO)
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--solo", nargs="*", help="Siglas a procesar (por defecto, todas las activas).")
    ap.add_argument("--archivo", action="append", default=[],
                    help="SIGLA=ruta.html para procesar un HTML ya descargado (sin red).")
    ap.add_argument("--pausa", type=float, default=2.0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    archivos = dict(a.split("=", 1) for a in args.archivo)
    normas = [n for n in leer_catalogo(args.catalogo) if n.activa]
    if args.solo:
        normas = [n for n in normas if n.sigla in set(args.solo)]
    args.salida.mkdir(parents=True, exist_ok=True)
    manifiesto_ruta = args.salida / "manifiesto.json"
    manifiesto = json.loads(manifiesto_ruta.read_text(encoding="utf-8")) if manifiesto_ruta.exists() else {}

    errores = 0
    for i, norma in enumerate(normas):
        if norma.sigla not in archivos and not norma.url:
            log.info("%s: sin norma_id en el catálogo; se omite", norma.sigla)
            continue
        if i and norma.sigla not in archivos:
            time.sleep(args.pausa)
        try:
            html = Path(archivos[norma.sigla]).read_bytes() if norma.sigla in archivos else None
            resumen = cargar_norma(norma, args.salida, html=html)
        except Exception as e:  # noqa: BLE001 — una norma fallida no detiene las demás
            errores += 1
            log.error("%s: %s", norma.sigla, e)
            manifiesto.setdefault(norma.sigla, {})["ultimo_error"] = str(e)[:500]
            continue
        previo = manifiesto.get(norma.sigla, {})
        resumen["actualizado_en"] = resumen["actualizado_en"] or previo.get("actualizado_en")
        manifiesto[norma.sigla] = resumen
        log.info("%s: %d artículos %s · cambios %s", norma.sigla, resumen["articulos"],
                 resumen["estados"], resumen["cambios"])

    manifiesto_ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return 2 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
