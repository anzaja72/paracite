from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TipoDocumento(str, Enum):
    norma = "norma"
    doctrina = "doctrina"
    sentencia_fixture = "sentencia_fixture"


class TipoCoincidencia(str, Enum):
    fundamento_directo = "fundamento_directo"
    cita_parcial = "cita_parcial"
    analogia = "analogia"
    contrario = "contrario"
    no_soporta = "no_soporta"


class CiteRequest(BaseModel):
    tesis: str = Field(..., min_length=1, description="Tesis jurídica en lenguaje natural.")
    jurisdiccion: str = Field(default="ES")
    tipos: list[TipoDocumento] | None = None
    umbral_confianza: float = Field(default=0.87, ge=0, le=1)
    max_resultados: int = Field(default=3, ge=1, le=20)
    incluir_texto_completo: bool = False

    @field_validator("tesis")
    @classmethod
    def tesis_no_vacia(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("tesis no puede estar vacía")
        return stripped

    @field_validator("jurisdiccion")
    @classmethod
    def jurisdiccion_upper(cls, value: str) -> str:
        return value.strip().upper() or "ES"


class CiteMatch(BaseModel):
    id: str
    tipo: str
    confianza: float
    cita_formal: str
    parrafo_exacto: str
    enlace_profundo: str
    metadatos: dict[str, Any]


class CiteResponse(BaseModel):
    request_id: str
    tesis: str
    matches: list[CiteMatch]
    sin_match_alta_confianza: bool
    tiempo_procesamiento_ms: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    checks: dict[str, str]


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    window_seconds: int = 60


class MeResponse(BaseModel):
    key_id: str
    nombre: str
    plan: str
    jurisdiccion_default: str = "ES"
    rate_limit: RateLimitInfo
    uso: dict[str, int]


class IngestRequest(BaseModel):
    titulo: str = Field(..., min_length=1)
    texto: str = Field(..., min_length=1)
    jurisdiccion: str = "ES"
    tipo: TipoDocumento = TipoDocumento.norma
    materia: str | None = None


class IngestAccepted(BaseModel):
    job_id: str
    status: str = "queued"
    queued_at: datetime


class IngestDisabled(BaseModel):
    detail: str
    code: str = "INGEST_NOT_ENABLED"


class JevClassification(BaseModel):
    chunk_id: str
    relevancia_semantica: float = Field(ge=0, le=1)
    es_cita_valida_alta_precision: bool
    tipo_coincidencia: TipoCoincidencia
    explicacion_corta: str | None = None


class Afirmacion(BaseModel):
    id: str | None = Field(default=None, description="Identificador opcional del tramo.")
    texto: str = Field(..., min_length=1, description="Afirmación o tramo del documento generado.")
    cita: str | None = Field(
        default=None,
        description="Cita tal como figura en el documento, si viene aparte del texto.",
    )

    @field_validator("texto")
    @classmethod
    def texto_no_vacio(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("texto no puede estar vacío")
        return stripped

    @field_validator("cita")
    @classmethod
    def cita_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class RevisarRequest(BaseModel):
    texto: str | None = Field(
        default=None,
        description="Documento generado. Sin afirmaciones, se revisa cada párrafo.",
    )
    afirmaciones: list[Afirmacion] | None = Field(
        default=None,
        description="Tramos de cita o afirmación. Si vienen, no se parte el texto.",
    )
    jurisdiccion: str | None = Field(
        default=None,
        description=(
            "Filtro opcional (CO, ES, …). Si se omite, se usan todos los chunks cargados. "
            "El seed de demostración es ES y no es derecho colombiano."
        ),
    )
    umbral_confianza: float = Field(default=0.87, ge=0, le=1)

    @field_validator("jurisdiccion")
    @classmethod
    def jurisdiccion_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @model_validator(mode="after")
    def require_input(self):
        texto = (self.texto or "").strip()
        self.texto = texto or None
        if self.texto is None and not self.afirmaciones:
            raise ValueError("hace falta texto o afirmaciones")
        return self


class _RevisionBase(BaseModel):
    id: str
    texto: str = Field(description="Tramo recibido, sin reescritura.")
    confianza: float
    indicacion: str


class RevisionDejar(_RevisionBase):
    estado: Literal["dejar"] = "dejar"


class RevisionNoSostiene(_RevisionBase):
    estado: Literal["no_sostiene"] = "no_sostiene"


class RevisionCompletar(_RevisionBase):
    estado: Literal["completar"] = "completar"
    chunk_id: str
    cita_formal: str
    parrafo_exacto: str
    enlace_profundo: str


RevisionItem = Annotated[
    RevisionCompletar | RevisionDejar | RevisionNoSostiene,
    Field(discriminator="estado"),
]


class RevisarResponse(BaseModel):
    request_id: str
    jurisdiccion: str | None = None
    resultados: list[RevisionItem]
    tiempo_procesamiento_ms: int
