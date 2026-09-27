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
    fuente: str              # funcionpublica | senado
    norma_id: str | None = None  # Función Pública: parámetro ?i=
    archivos: list[str] = field(default_factory=list)  # Senado: ley_0100_1993.html (candidatos en orden)
    tipo: str | None = None      # ley | decreto | decreto_ley
    numero: str | None = None
    anio: str | None = None
    grupo: str | None = None     # rama del derecho (para el catálogo)
    activa: bool = True

    @property
    def url(self) -> str | None:
        if self.fuente == "funcionpublica" and self.norma_id:
            return f"https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i={self.norma_id}"
        if self.fuente == "senado" and self.candidatos_senado:
            return "http://www.secretariasenado.gov.co/senado/basedoc/" + self.candidatos_senado[0]
        return None

    @property
    def candidatos_senado(self) -> list[str]:
        """Archivos a probar en el Senado: los explícitos y los derivados de tipo/número/año."""
        out = list(self.archivos)
        if self.numero and self.anio:
            n = f"{int(self.numero):04d}"
            if self.tipo in (None, "ley"):
                out.append(f"ley_{n}_{self.anio}.html")
            if self.tipo in ("decreto", "decreto_ley"):
                out.append(f"decreto_{n}_{self.anio}.html")
                out.append(f"decreto_ley_{n}_{self.anio}.html")
        return list(dict.fromkeys(out))


@dataclass
class Articulo:
    numero: str                                   # "64", "5A", "T-12" (transitorio)
    parrafos: list[str]
    ruta: list[str] = field(default_factory=list)  # Título › Capítulo…
    notas_vigencia: list[str] = field(default_factory=list)
    referencias: list[str] = field(default_factory=list)
    jurisprudencia: list[str] = field(default_factory=list)
    texto_anterior: list[str] = field(default_factory=list)
    epigrafe: str | None = None                   # «CONTRATO ESCRITO», «TARIFA PARA USUARIOS…»

    @property
    def texto(self) -> str:
        return "\n".join(self.parrafos)

    @property
    def estado(self) -> str:
        notas = " ".join(self.notas_vigencia).upper()
        inicio = (self.parrafos[0] if self.parrafos else "").upper()
        if re.search(r"ART[ÍI]CULO\s+(DECLARADO\s+)?INEXEQUIBLE", inicio + " " + notas):
            return "inexequible"
        if re.search(r"ART[ÍI]CULO\s+DEROGADO", inicio + " " + notas):
            return "derogado"
        # Nota al comienzo del texto, sin la palabra ARTÍCULO: «Derogado por el Art. 40…» (Ley 153 de 1887)
        if re.match(r"\s*DEROGADO\b", inicio):
            return "derogado"
        if not self.parrafos:
            return "sin_texto_en_fuente"
        if re.search(r"MODIFICADO|SUSTITUIDO|ADICIONADO|SUBROGADO", notas):
            return "modificado"
        if re.match(r"\s*(ART[ÍI]CULO\s+)?(MODIFICADO|SUSTITUIDO|SUBROGADO)\s+POR\b", inicio):
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
    if art.epigrafe:
        titulo += f". {art.epigrafe.capitalize() if art.epigrafe.isupper() else art.epigrafe}"
    elif art.ruta:
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
            "epigrafe": art.epigrafe,
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
