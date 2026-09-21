from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
