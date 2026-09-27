"""Modelo común del corpus: un fragmento por artículo, listo para ParaCite (formato de seed.json)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NormaCatalogo:
    """Entrada del catálogo (corpus/co/catalogo.yaml)."""

    sigla: str               # CP, CST, CGP…  (se usa en los IDs: co-cp-art-64)
    nombre: str              # Constitución Política de Colombia
    cita: str                # forma corta para la cita formal: «Constitución Política»
    materia: str
    fuente: str              # funcionpublica
    norma_id: str | None     # id en la fuente (Función Pública: parámetro ?i=)
    activa: bool = True

    @property
    def url(self) -> str | None:
        if self.fuente == "funcionpublica" and self.norma_id:
            return f"https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i={self.norma_id}"
        return None


@dataclass
class Articulo:
    numero: str                                   # "64", "5A", "T-12" (transitorio)
    parrafos: list[str]
    ruta: list[str] = field(default_factory=list)  # Título › Capítulo…
    notas_vigencia: list[str] = field(default_factory=list)
    referencias: list[str] = field(default_factory=list)
    jurisprudencia: list[str] = field(default_factory=list)
    texto_anterior: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.parrafos)

    @property
    def estado(self) -> str:
        notas = " ".join(self.notas_vigencia).upper()
        inicio = (self.parrafos[0] if self.parrafos else "").upper()
        if re.search(r"^\(?\s*ART[ÍI]CULO\s+INEXEQUIBLE", inicio) or "(ARTÍCULO INEXEQUIBLE" in notas:
            return "inexequible"
        if re.search(r"ART[ÍI]CULO\s+DEROGADO|<\s*ART[ÍI]CULO\s+DEROGADO", inicio) or \
           re.search(r"\(ART[ÍI]CULO\s+DEROGADO", notas):
            return "derogado"
        if "MODIFICADO" in notas or "SUSTITUIDO" in notas or "ADICIONADO" in notas:
            return "modificado"
        return "vigente"


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _slug(valor: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", valor.lower()).strip("-")


def a_fragmento(norma: NormaCatalogo, art: Articulo, *, url: str, capturado_en: str) -> dict[str, Any]:
    """Convierte un artículo al formato de chunk que carga LocalBm25Store."""
    numero_cita = f"art. transitorio {art.numero[2:]}" if art.numero.startswith("T-") else f"art. {art.numero}"
    titulo = f"{norma.nombre}, {numero_cita}"
    if art.ruta:
        titulo += f" — {art.ruta[-1]}"
    ancla = art.numero if not art.numero.startswith("T-") else ""
    return {
        "id": f"co-{_slug(norma.sigla)}-art-{_slug(art.numero)}",
        "tipo": "norma",
        "jurisdiccion": "CO",
        "materia": norma.materia,
        "titulo": titulo,
        "cita_formal": f"{norma.cita}, {numero_cita}",
        "parrafo": art.texto,
        "texto_completo": art.texto,
        "enlace_profundo": f"{url}#{ancla}" if ancla else url,
        "metadatos": {
            "fuente": norma.fuente,
            "fuente_oficial": True,
            "url_oficial": url,
            "norma": norma.sigla,
            "norma_nombre": norma.nombre,
            "articulo": art.numero,
            "ruta": art.ruta,
            "estado": art.estado,
            "notas_vigencia": art.notas_vigencia,
            "referencias": art.referencias,
            "jurisprudencia": art.jurisprudencia,
            "texto_anterior": art.texto_anterior,
            "parrafos": art.parrafos,
            "capturado_en": capturado_en,
            "huella": huella(art.texto),
        },
    }


def a_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)
