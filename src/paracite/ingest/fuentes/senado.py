"""Procesador de la Secretaría del Senado (secretariasenado.gov.co/senado/basedoc, edición de Avance Jurídico).

Estructura observada (codigo_sustantivo_trabajo.html):
- Direcciones predecibles: ley_0100_1993.html, decreto_1072_2015.html, codigo_civil.html…
- Las normas largas se dividen en partes enlazadas con «Siguiente»: <nombre>_pr001.html, _pr002…
- Cada artículo: <p><a class="bookmarkaj" name="3">ARTICULO 3o. RELACIONES QUE REGULA.</a> texto…</p>
  (o <p><b><a name="4">ARTÍCULO 4o. <span class="i_aj">EPÍGRAFE.</span></a></b> texto…</p>).
- Notas de vigencia en línea, entre < >: «<Artículo modificado por el artículo 2 de la Ley 2466 de 2025.
  El nuevo texto es el siguiente:>» — se extraen como notas y se quitan del texto.
- Los bloques «Notas de Vigencia» / «Jurisprudencia Vigencia» / «Legislación Anterior» se llenan con
  JavaScript (tablas vacías en el HTML): se ignoran.
- Títulos y capítulos: <p class="centrado"><span class="b_aj">TITULO PRELIMINAR.</span></p>.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from paracite.ingest.fuentes.funcionpublica import ARTICULO as _ARTICULO
from paracite.ingest.fuentes.funcionpublica import _Ruta, numero_articulo
from paracite.ingest.modelo import Articulo

BASE = "http://www.secretariasenado.gov.co/senado/basedoc/"

# Notas editoriales en línea: <Artículo modificado por…>, <Inciso derogado por…>, <Aparte tachado INEXEQUIBLE>
_NOTA = re.compile(
    r"<\s*((?:Art[íi]culo|Inciso|Par[áa]grafo|Numeral|Literal|Aparte|Texto|Expresi[óo]n|Ordinal|Cap[íi]tulo)"
    r"[^<>]{0,600}?)>",
    re.IGNORECASE,
)
_PALABRAS_NOTA = re.compile(
    r"modificad|adicionad|derogad|subrogad|sustituid|inexequible|exequible|suspendid|nulo|tachado|subrayado",
    re.IGNORECASE,
)


def decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def url_de(archivo: str) -> str:
    return urljoin(BASE, archivo)


def siguiente_parte(html: str, url_actual: str) -> str | None:
    """Dirección de la parte siguiente («Siguiente» → *_pr00N.html), si existe."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower() == "siguiente" and "_pr" in a["href"]:
            return urljoin(url_actual, a["href"])
    return None


def _texto(nodo: Tag) -> str:
    return " ".join(nodo.get_text(" ", strip=True).split())


def _separar_notas(texto: str) -> tuple[str, list[str]]:
    notas: list[str] = []

    def quitar(m: re.Match) -> str:
        contenido = m.group(1).strip()
        if _PALABRAS_NOTA.search(contenido):
            notas.append(contenido)
            return " "
        return m.group(0)

    limpio = _NOTA.sub(quitar, texto)
    return " ".join(limpio.split()), notas


def procesar(html: str) -> list[Articulo]:
    """Procesa una página (o varias partes concatenadas) del Senado."""
    soup = BeautifulSoup(html, "html.parser")
    articulos: list[Articulo] = []
    vistos: set[str] = set()
    ruta = _Ruta()
    actual: Articulo | None = None

    for nodo in soup.find_all(["p", "li", "table"]):
        if nodo.name in ("p", "li") and nodo.find_parent(["table", "li"]) is not None:
            continue
        clases = nodo.get("class") or []
        if nodo.name == "table":
            if any(c.startswith("caja_vja") for c in clases):
                continue  # notas/jurisprudencia cargadas por JavaScript (vacías)
            filas = [" | ".join(_texto(c) for c in tr.find_all(["td", "th"])) for tr in nodo.find_all("tr")]
            texto = "\n".join(f for f in filas if f.strip(" |"))
        else:
            texto = _texto(nodo)
        if not texto:
            continue
        if texto.lower() in ("siguiente", "anterior") or re.fullmatch(r"(anterior\s*)?siguiente|anterior", texto.lower()):
            continue

        ancla = nodo.find("a", attrs={"name": True}) if nodo.name == "p" else None
        titulo_ancla = _texto(ancla) if ancla is not None else ""
        m = _ARTICULO.match(titulo_ancla) if titulo_ancla else None
        if m and (m.group(1) or m.group(2)):
            numero = numero_articulo(m, articulos)
            if numero == "1" and "1" in vistos and len(articulos) <= 5:
                articulos.clear()
                vistos.clear()
            if numero in vistos:
                actual = None
                continue
            epigrafe = titulo_ancla[m.end():].strip(" .-") or None
            idx = texto.find(titulo_ancla)
            cuerpo = texto[idx + len(titulo_ancla):] if idx >= 0 else texto
            cuerpo, notas = _separar_notas(cuerpo.lstrip(" .-").rstrip())
            actual = Articulo(numero=numero, parrafos=[cuerpo] if cuerpo else [], ruta=ruta.actual(),
                              notas_vigencia=notas, epigrafe=epigrafe)
            vistos.add(numero)
            articulos.append(actual)
            continue

        if nodo.name == "p" and "centrado" in clases:
            if not texto.startswith("<"):
                ruta.agregar(texto.rstrip(" ."))
                actual = None
            continue

        if actual is None:
            continue
        texto, notas = _separar_notas(texto)
        actual.notas_vigencia.extend(notas)
        if texto:
            actual.parrafos.append(texto)

    return [a for a in articulos if a.parrafos or a.epigrafe]
