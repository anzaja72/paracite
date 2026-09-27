"""Exporta el corpus colombiano a documentos Markdown para la biblioteca de un agente (Chipp.ai u otro).

Uso:
    uv run python -m paracite.ingest.exportar_chipp                         # todo el corpus
    uv run python -m paracite.ingest.exportar_chipp --paquete esencial      # códigos y leyes principales
    uv run python -m paracite.ingest.exportar_chipp --solo CST CGP --max-mb 3

Salida (por defecto exportacion/chipp/):
    00_INDICE.md                  qué normas hay, cuántos artículos, fecha de corte y cómo citar
    <grupo>/<SIGLA>.md            una norma por archivo…
    <grupo>/<SIGLA>_parte02.md    …dividida en partes si supera --max-mb

Cada artículo queda como un bloque autocontenido (cita formal, estado, notas de vigencia, texto y
enlace oficial) para que el buscador de la biblioteca lo recupere completo aunque corte el documento.
Los artículos derogados o inexequibles se incluyen marcados «NO VIGENTE» para que el agente no los
cite como derecho vigente.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from paracite.ingest.cargar import CATALOGO, SALIDA

DESTINO = Path("exportacion") / "chipp"

# Códigos y leyes de uso diario: primer paquete recomendado para la biblioteca.
ESENCIAL = [
    "CP", "CC", "DL-410-1971", "CST", "CPTSS", "CGP", "CPACA", "ET", "LEY-599-2000", "LEY-906-2004",
    "LEY-600-2000", "LEY-1098-2006", "LEY-100-1993", "LEY-80-1993",
    "LEY-1150-2007", "LEY-1474-2011", "LEY-1952-2019", "LEY-2213-2022", "LEY-2220-2022", "LEY-1480-2011",
    "LEY-1581-2012", "LEY-1116-2006", "LEY-1258-2008", "LEY-2466-2025", "LEY-2381-2024", "LEY-153-1887",
    "LEY-54-1990", "LEY-675-2001", "LEY-820-2003", "LEY-1996-2019", "DEC-1072-2015", "DEC-1625-2016",
]

ESTADOS = {
    "vigente": "Vigente",
    "modificado": "Vigente (modificado)",
    "derogado": "NO VIGENTE — derogado",
    "inexequible": "NO VIGENTE — declarado inexequible",
    "sin_texto_en_fuente": "Sin texto publicado en la fuente oficial",
}


def _slug(texto: str) -> str:
    texto = texto.lower()
    for a, b in zip("áéíóúñü", "aeiounu"):
        texto = texto.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")[:60] or "otros"


def _grupos() -> dict[str, str]:
    """{sigla: grupo} según el catálogo."""
    datos = yaml.safe_load(CATALOGO.read_text(encoding="utf-8")) if CATALOGO.exists() else {}
    normas = datos.get("normas", [])
    # Las normas sin «grupo» (los códigos de Función Pública) toman el grupo de su materia.
    por_materia: dict[str, str] = {}
    for n in normas:
        if n.get("grupo") and n.get("materia"):
            por_materia.setdefault(n["materia"], n["grupo"])
    return {n["sigla"]: n.get("grupo") or por_materia.get(n.get("materia"), "Otros") for n in normas}


def bloque_articulo(frag: dict) -> str:
    md = frag["metadatos"]
    estado = ESTADOS.get(md.get("estado"), md.get("estado") or "")
    lineas = [f"### {frag['cita_formal']}"]
    if md.get("epigrafe"):
        lineas.append(f"**Epígrafe:** {md['epigrafe']}")
    lineas.append(f"**Estado:** {estado}")
    if md.get("ruta"):
        lineas.append(f"**Ubicación:** {' › '.join(md['ruta'])}")
    for nota in md.get("notas_vigencia") or []:
        lineas.append(f"**Nota de vigencia:** {nota}")
    lineas.append("")
    texto = frag.get("texto_completo") or ""
    lineas.append(texto if texto else "_(La fuente oficial no publica el texto de este artículo.)_")
    lineas.append("")
    lineas.append(f"Fuente oficial: {frag.get('enlace_profundo') or md.get('url_oficial', '')}")
    return "\n".join(lineas)


def _encabezado(nombre: str, sigla: str, info: dict, parte: int, total: int, corte: str) -> str:
    partes = f" — parte {parte} de {total}" if total > 1 else ""
    etiquetas = {"vigente": "vigentes", "modificado": "modificados", "derogado": "derogados",
                 "inexequible": "inexequibles", "sin_texto_en_fuente": "sin texto en la fuente"}
    estados = ", ".join(f"{etiquetas.get(k, k)}: {v}" for k, v in sorted((info.get("estados") or {}).items()))
    return "\n".join([
        f"# {nombre}{partes}",
        "",
        f"- Sigla en el corpus: {sigla}",
        f"- Fuente oficial: {info.get('url', '')}",
        f"- Fecha de corte: {corte}",
        f"- Artículos: {info.get('articulos', '?')} ({estados})",
        ("- Texto tomado de la fuente oficial, un artículo por bloque. Los artículos marcados «NO VIGENTE» "
         "se incluyen solo como referencia histórica."),
        "",
        "---",
        "",
    ])


def exportar_norma(ruta_jsonl: Path, destino: Path, info: dict, *, max_bytes: int, corte: str) -> list[Path]:
    """Escribe la norma (en una o varias partes) y completa `info` con nombre y nº de artículos."""
    filas = [json.loads(l) for l in ruta_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not filas:
        return []
    sigla = ruta_jsonl.stem
    nombre = filas[0]["metadatos"].get("norma_nombre") or sigla
    info.setdefault("nombre", nombre)
    info["articulos"] = len(filas)
    if not info.get("estados"):
        for f in filas:
            e = f["metadatos"].get("estado")
            info.setdefault("estados", {})[e] = info.get("estados", {}).get(e, 0) + 1
    bloques = [bloque_articulo(f) for f in filas]

    # Se reparte en partes sin cortar artículos.
    partes: list[list[str]] = [[]]
    tam = 0
    for b in bloques:
        n = len(b.encode("utf-8")) + 2
        if partes[-1] and tam + n > max_bytes:
            partes.append([])
            tam = 0
        partes[-1].append(b)
        tam += n

    destino.mkdir(parents=True, exist_ok=True)
    escritos = []
    for i, contenido in enumerate(partes, 1):
        archivo = destino / (f"{sigla}.md" if len(partes) == 1 else f"{sigla}_parte{i:02d}.md")
        archivo.write_text(_encabezado(nombre, sigla, info, i, len(partes), corte)
                           + "\n\n".join(contenido) + "\n", encoding="utf-8")
        escritos.append(archivo)
    return escritos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exporta el corpus CO a Markdown para la biblioteca de un agente.")
    ap.add_argument("--corpus", type=Path, default=SALIDA)
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--solo", nargs="*", help="Siglas a exportar.")
    ap.add_argument("--paquete", choices=["esencial", "todo"], default="todo")
    ap.add_argument("--max-mb", type=float, default=5.0, help="Tamaño máximo por archivo (MB).")
    args = ap.parse_args(argv)

    manifiesto_ruta = args.corpus / "manifiesto.json"
    manifiesto = json.loads(manifiesto_ruta.read_text(encoding="utf-8")) if manifiesto_ruta.exists() else {}
    grupos = _grupos()
    siglas = [p.stem for p in sorted(args.corpus.glob("*.jsonl"))]
    if args.paquete == "esencial":
        siglas = [s for s in ESENCIAL if s in siglas]
    if args.solo:
        siglas = [s for s in siglas if s in set(args.solo)]

    corte = datetime.now(UTC).date().isoformat()
    if args.destino.exists():
        shutil.rmtree(args.destino)
    args.destino.mkdir(parents=True)

    indice: dict[str, list[tuple[str, dict, list[Path]]]] = {}
    for sigla in siglas:
        info = dict(manifiesto.get(sigla, {}))
        grupo = grupos.get(sigla, "Otros")
        archivos = exportar_norma(args.corpus / f"{sigla}.jsonl", args.destino / _slug(grupo), info,
                                  max_bytes=int(args.max_mb * 1024 * 1024),
                                  corte=(info.get("verificado_en") or corte)[:10])
        if archivos:
            indice.setdefault(grupo, []).append((sigla, info, archivos))

    total_arts = sum(i.get("articulos", 0) for g in indice.values() for _, i, _ in g)
    total_archivos = sum(len(a) for g in indice.values() for _, _, a in g)
    lineas = [
        "# Corpus normativo colombiano — índice",
        "",
        (f"Fecha de corte: {corte}. {sum(len(g) for g in indice.values())} normas, {total_arts} artículos, "
         f"{total_archivos} archivos."),
        "",
        ("Fuentes oficiales: Función Pública (Gestor Normativo) y Secretaría del Senado (Avance Jurídico). "
         "Cada artículo aparece como un bloque «### <cita formal>» con su estado de vigencia, las notas de "
         "vigencia y el enlace a la fuente oficial."),
        "",
    ]
    for grupo in sorted(indice):
        lineas += [f"## {grupo}", ""]
        for sigla, info, archivos in sorted(indice[grupo], key=lambda x: x[0]):
            nombre = info.get("nombre") or sigla
            lineas.append(f"- **{nombre}** ({info.get('articulos', '?')} artículos) — "
                          + ", ".join(a.relative_to(args.destino).as_posix() for a in archivos))
        lineas.append("")
    (args.destino / "00_INDICE.md").write_text("\n".join(lineas), encoding="utf-8")

    tam = sum(p.stat().st_size for p in args.destino.rglob("*.md"))
    mayor = max(args.destino.rglob("*.md"), key=lambda p: p.stat().st_size)
    print(f"Exportadas {sum(len(g) for g in indice.values())} normas ({total_arts} artículos) en "
          f"{total_archivos + 1} archivos, {tam / 1e6:.1f} MB, en {args.destino}/")
    print(f"Archivo más grande: {mayor.relative_to(args.destino)} ({mayor.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
