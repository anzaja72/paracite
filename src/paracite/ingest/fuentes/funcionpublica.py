"""Procesador del Gestor Normativo de Función Pública (funcionpublica.gov.co/eva/gestornormativo).

Estructura observada (Constitución, norma.php?i=4125):
- Cada artículo empieza con  <p><strong>ARTÍCULO <a id="64"></a>64.</strong> texto…</p>
- Los bloques ocultos <div id="jurisNNNN"> («Norma Anterior», «Jurisprudencia Vigencia»…) van
  precedidos por un <button onClick="mostrar_ocultar_jurisprudencia(NNNN)">. NO son texto vigente:
  se guardan como metadatos y se quitan del documento antes de leer los artículos.
- Notas de vigencia: «(Artículo MODIFICADO por el Art. 1 del Acto Legislativo 01 de 2023)».
- Referencias: «(Ver Ley 41 de 1993)».
- Títulos y capítulos: <p align="center"><strong>TITULO II …</strong></p>.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from paracite.ingest.modelo import Articulo

_ARTICULO = re.compile(
    r"^\s*ART[ÍI]CULO\s*(TRANSITORIO\s*)?(\d+(?:-\d+)?(?-i:[A-Z])?(?:[-\s]?BIS)?)?\s*(?:[oº°](?![A-Za-zÁÉÍÓÚÑáéíóúñ]))?\s*\.?",
    re.IGNORECASE,
)
_NOTA_VIGENCIA = re.compile(
    r"^\(\s*(?:Art[íi]culo|Inciso|Par[áa]grafo|Numeral|Literal|Texto|Modificado|Adicionado|Derogado|Subrogado)[^)]*"
    r"(?:MODIFICADO|ADICIONADO|DEROGADO|SUSTITUIDO|SUBROGADO|INEXEQUIBLE|EXEQUIBLE|REGLAMENTADO)",
    re.IGNORECASE,
)
_REFERENCIA = re.compile(r"^\(\s*Ver\b", re.IGNORECASE)
_ENCABEZADO = re.compile(r"^(LIBRO|PARTE|T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N)\b", re.IGNORECASE)
_NIVEL = {"LIBRO": 0, "PARTE": 0, "TITULO": 1, "TÍTULO": 1, "CAPITULO": 2, "CAPÍTULO": 2,
          "SECCION": 3, "SECCIÓN": 3}


def decodificar(contenido: bytes) -> str:
    """La página declara ISO-8859-1 pero suele venir en UTF-8: se prueba UTF-8 primero."""
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def _texto(nodo: Tag) -> str:
    return " ".join(nodo.get_text(" ", strip=True).split())


def _texto_tabla(tabla: Tag) -> str:
    filas = []
    for tr in tabla.find_all("tr"):
        celdas = [_texto(c) for c in tr.find_all(["td", "th"])]
        if any(celdas):
            filas.append(" | ".join(celdas))
    return "\n".join(filas)


def _extraer_bloques_ocultos(soup: BeautifulSoup) -> dict[str, tuple[str, str]]:
    """{id_div: (tipo_bloque, texto)} y los quita del árbol."""
    bloques: dict[str, tuple[str, str]] = {}
    for boton in soup.find_all("button", onclick=re.compile(r"mostrar_ocultar_jurisprudencia")):
        m = re.search(r"\((\d+)\)", boton.get("onclick", ""))
        if not m:
            continue
        div = soup.find(id=f"juris{m.group(1)}")
        tipo = _texto(boton)
        if div is not None:
            cuerpo = div.find(class_="card-body") or div
            bloques[div.get("id")] = (tipo, _texto(cuerpo))
            div.attrs["data-bloque"] = div.get("id")
        boton.attrs["data-bloque"] = f"juris{m.group(1)}"
    return bloques


def procesar(html: str) -> list[Articulo]:
    soup = BeautifulSoup(html, "html.parser")
    bloques = _extraer_bloques_ocultos(soup)

    articulos: list[Articulo] = []
    ruta = _Ruta()
    actual: Articulo | None = None
    vistos: set[str] = set()
    usados: set[str] = set()

    def adjuntar(clave: str | None) -> None:
        if actual is None or not clave or clave not in bloques or clave in usados:
            return
        usados.add(clave)
        tipo, texto = bloques[clave]
        if "anterior" in tipo.lower():
            actual.texto_anterior.append(texto)
        elif texto:
            actual.jurisprudencia.append(texto)

    for nodo in soup.find_all(["p", "li", "table", "button"]):
        if nodo.decomposed:
            continue
        if nodo.name != "button" and nodo.find_parent(id=re.compile(r"^juris\d+")) is not None:
            continue  # contenido de un bloque oculto (norma anterior, jurisprudencia)
        if nodo.name in ("p", "li") and nodo.find_parent(["table", "li"]) is not None:
            continue  # ya incluido en la tabla o en el ítem de lista que lo contiene
        if nodo.name == "button":
            adjuntar(nodo.get("data-bloque"))
            continue

        # Bloques ocultos anidados dentro del propio <p>: se adjuntan y se quitan del texto.
        for boton in nodo.find_all("button", attrs={"data-bloque": True}):
            adjuntar(boton.get("data-bloque"))
        for oculto in nodo.find_all(attrs={"data-bloque": True}):
            oculto.decompose()

        texto = _texto_tabla(nodo) if nodo.name == "table" else _texto(nodo)
        if not texto:
            continue

        fuerte = nodo.find("strong") if nodo.name == "p" else None
        encabezado_art = _ARTICULO.match(_texto(fuerte)) if fuerte is not None else None
        if encabezado_art and (encabezado_art.group(1) or encabezado_art.group(2)):
            numero = (encabezado_art.group(2) or "").replace(" ", "").upper()
            if encabezado_art.group(1):
                numero = f"T-{numero or len([a for a in articulos if a.numero.startswith('T-')]) + 1}"
            if numero == "1" and "1" in vistos and len(articulos) <= 5:
                # La numeración reinicia: lo anterior era el decreto/ley que adopta el código
                # (p. ej. Decreto 624 de 1989 → Estatuto Tributario). Se conserva solo el código.
                articulos.clear()
                vistos.clear()
            if numero in vistos:  # repetido fuera de bloque: se conserva el primero (vigente)
                actual = None
                continue
            titulo_fuerte = _texto(fuerte)
            epigrafe = titulo_fuerte[encabezado_art.end():].strip(" .-")
            cuerpo = texto[len(titulo_fuerte):].strip(" .-")
            fuertes = nodo.find_all("strong")
            if not epigrafe and len(fuertes) > 1 and cuerpo.startswith(_texto(fuertes[1])):
                epigrafe = _texto(fuertes[1]).strip(" .-")      # ET: <strong>240-1.</strong><strong>TARIFA…</strong>
                cuerpo = cuerpo[len(_texto(fuertes[1])):].strip(" .-")
            actual = Articulo(numero=numero, parrafos=[cuerpo] if cuerpo else [], ruta=ruta.actual(),
                              epigrafe=epigrafe or None)
            vistos.add(numero)
            articulos.append(actual)
            continue

        if nodo.name == "p" and (nodo.get("align") or "").lower() == "center":
            if not texto.lower().startswith("ver "):
                ruta.agregar(texto)
                actual = None
            continue

        if actual is None:
            continue
        if _NOTA_VIGENCIA.match(texto):
            actual.notas_vigencia.append(texto)
        elif _REFERENCIA.match(texto):
            actual.referencias.append(texto)
        else:
            actual.parrafos.append(texto)

    # Se conservan los artículos con solo epígrafe (existen en la fuente aunque sin texto publicado).
    return [a for a in articulos if a.parrafos or a.epigrafe]


class _Ruta:
    """Título y capítulo vigentes según los encabezados centrados.

    En el Gestor Normativo los títulos suelen venir solo con su descripción («DE LOS PRINCIPIOS
    FUNDAMENTALES») y los capítulos como «CAPÍTULO 2.» seguido de su descripción.
    """

    def __init__(self) -> None:
        self.titulo: str | None = None
        self.capitulo: str | None = None
        self._pendiente: str | None = None  # «CAPÍTULO 2.» / «TÍTULO III» a la espera de su nombre

    def agregar(self, texto: str) -> None:
        texto = texto.strip()
        m = _ENCABEZADO.match(texto)
        if m:
            nivel = _NIVEL.get(m.group(1).upper(), 3)
            if nivel <= 1:
                self.titulo, self.capitulo = texto.rstrip("."), None
            else:
                self.capitulo = texto.rstrip(".")
            self._pendiente = "titulo" if nivel <= 1 else "capitulo"
            return
        if self._pendiente == "capitulo" and self.capitulo:
            self.capitulo = f"{self.capitulo}. {texto}"
        elif self._pendiente == "titulo" and self.titulo:
            self.titulo = f"{self.titulo}. {texto}"
        else:
            self.titulo, self.capitulo = texto, None
        self._pendiente = None

    def actual(self) -> list[str]:
        return [x for x in (self.titulo, self.capitulo) if x]
