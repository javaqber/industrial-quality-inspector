"""
IQI — API principal (Fase 0B)
================================
FastAPI backend for IQI Aluminium visual quality inspection.

Stack: FastAPI → Claude Vision (Anthropic) → PostgreSQL (shared with AuraPredict)

Changes from Fase 0B:
  - init_iqi_db() now called in FastAPI lifespan (not at import time).
  - CORS restricted to explicit allowed origins (env-configurable).
  - Image size limit: MAX_IMAGE_BYTES (default 10 MB per image).
  - Image file validation: content-type check + magic-bytes check.
  - Logging replaces print() throughout.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database_iqi import (
    obtener_tipos_pieza, crear_tipo_pieza, obtener_defectos_tipo,
    registrar_analisis, obtener_historial_iqi,
    registrar_verificacion, obtener_stats_iqi,
    obtener_usuario_por_email, init_iqi_db,
)
from auth import verificar_token, verificar_password, crear_token

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../.env'))
load_dotenv()

logger = logging.getLogger(__name__)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Maximum bytes per uploaded image (default 10 MB).
# Set MAX_IMAGE_BYTES in .env to override.
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))

# Allowed image MIME types
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Magic bytes for supported image formats (first 4 bytes)
_MAGIC = {
    b"\xff\xd8\xff":   "image/jpeg",
    b"\x89PNG":        "image/png",
    b"GIF8":           "image/gif",
    b"RIFF":           "image/webp",   # RIFF....WEBP
}

# CORS: read allowed origins from env, default to localhost only.
# In production set: CORS_ORIGINS=https://app.empresa.com,https://inspector.empresa.com
_cors_env = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]


# ─── LIFESPAN ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise DB tables. Shutdown: nothing to clean up."""
    try:
        init_iqi_db()
        logger.info("IQI database ready.")
    except Exception as exc:
        logger.error("DB init failed (tables may already exist): %s", exc)
    yield


# ─── APP ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IQI — Industrial Quality Inspector API",
    description=(
        "API de inspección visual de calidad industrial con Claude Vision AI.\n\n"
        "**Flujo principal:**\n"
        "1. `POST /login` → obtén JWT\n"
        "2. `POST /iqi/analyze` → envía foto(s) → resultado OK/REVISAR/NOK\n"
        "3. `POST /iqi/verify` → confirma o corrige el resultado\n"
        "4. `GET /iqi/history` → trazabilidad completa\n"
        "5. `GET /iqi/stats` → estadísticas por empresa"
    ),
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── AUTH ─────────────────────────────────────────────────────────────────────

security = HTTPBearer()


def get_usuario_actual(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT and return the user payload."""
    payload = verificar_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    return payload


# ─── IMAGE VALIDATION ─────────────────────────────────────────────────────────

async def validate_image(img: UploadFile) -> bytes:
    """
    Read, size-check, and magic-byte-validate an uploaded image.

    Returns raw bytes if valid. Raises HTTPException otherwise.
    """
    raw = await img.read()

    # Size check
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Imagen '{img.filename}' demasiado grande "
                f"({len(raw) // 1024} KB). "
                f"Máximo: {MAX_IMAGE_BYTES // 1024 // 1024} MB."
            ),
        )

    # Empty file
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail=f"Imagen '{img.filename}' está vacía.")

    # Magic-bytes check (first 4 bytes)
    header = raw[:4]
    detected = None
    for magic, mime in _MAGIC.items():
        if header[:len(magic)] == magic:
            detected = mime
            break

    # Special WEBP: RIFF....WEBP
    if detected == "image/webp" and raw[8:12] != b"WEBP":
        detected = None

    if detected is None:
        raise HTTPException(
            status_code=415,
            detail=(
                f"'{img.filename}' no parece una imagen válida "
                "(se esperaba JPEG, PNG, GIF o WebP)."
            ),
        )

    return raw


# ─── PROMPT ───────────────────────────────────────────────────────────────────

def construir_prompt(tipo_pieza: str, defectos_conocidos: list) -> str:
    """Build the system prompt adapted to the piece type and known defects."""
    defectos_str = ""
    if defectos_conocidos:
        defectos_str = (
            f"\n\nDefectos específicos conocidos para '{tipo_pieza}':\n"
            + "\n".join(f"  - {d}" for d in defectos_conocidos)
        )

    return f"""Eres un inspector de calidad industrial de alta precisión para entornos de fabricación.
Analiza la imagen de la pieza de tipo "{tipo_pieza}" buscando defectos con el criterio de un técnico experimentado con años de experiencia en control de calidad industrial.
{defectos_str}

Clasifica en uno de estos tres niveles:
- OK: pieza sin defectos visibles, completamente apta para producción
- REVISAR: hay anomalías menores, la imagen no es suficientemente clara, o existe duda razonable — requiere verificación humana antes de aprobar
- NOK: defecto claro y definitivo detectado — la pieza debe descartarse o reprocesarse

Categorías de defectos generales a considerar:
  - Grietas o fisuras (superficiales o profundas)
  - Rayaduras superficiales (leves o graves)
  - Deformaciones geométricas (abolladuras, torsiones, desalineaciones)
  - Manchas, oxidación o contaminación superficial
  - Porosidad o burbujas (especialmente en aluminio extrusionado o piezas fundidas)
  - Rebabas o material sobrante en bordes y aristas
  - Acabado superficial deficiente (rugosidad anormal, irregularidades de color o textura)
  - Dimensiones visiblemente fuera de tolerancia

Si recibes varias imágenes, analízalas en conjunto para obtener una visión completa de la pieza.
En caso de duda entre dos clasificaciones, escoge siempre la más conservadora (NOK > REVISAR > OK).

El campo 'resumen' debe ser directo y tener un maximo de 10 palabras.
El campo 'accion' debe ser concreto y accionable en 1 frase.

Responde ÚNICAMENTE con este JSON exacto, sin markdown, sin texto adicional:
{{"resultado":"OK","confianza":90,"defecto":null,"zona":null,"accion":"Pieza aprobada. Continuar proceso.","resumen":"Sin defectos detectados"}}"""


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class VerificacionRequest(BaseModel):
    analisis_id: int
    resultado_ia: str
    resultado_operario: str


class TipoPiezaRequest(BaseModel):
    nombre: str
    descripcion: Optional[str] = ""
    defectos: Optional[List[str]] = []


# ─── STATIC FILES (PWA) ───────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "status":  "IQI API activa",
        "version": "1.1.0",
        "modelo":  "claude-sonnet-4-6",
    }


@app.get("/app")
def serve_app():
    """Serve the mobile PWA."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="PWA no encontrada.")
    return FileResponse(index_path)


@app.post("/login")
def login(req: LoginRequest):
    """Login with email and password. Returns JWT token."""
    usuario = obtener_usuario_por_email(req.email)
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas.")

    id_u, email_u, password_hash, nombre, rol, empresa_id, activo = usuario

    if not activo:
        raise HTTPException(status_code=401, detail="Cuenta desactivada.")

    if not verificar_password(req.password, password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas.")

    token = crear_token({
        "sub":        email_u,
        "nombre":     nombre,
        "rol":        rol,
        "empresa_id": empresa_id,
    })

    return {
        "access_token": token,
        "token_type":   "bearer",
        "nombre":       nombre,
        "rol":          rol,
        "empresa_id":   empresa_id,
    }


@app.post("/iqi/analyze")
async def analyze(
    tipo_pieza: str = Form(...),
    images: List[UploadFile] = File(...),
    usuario: dict = Depends(get_usuario_actual),
):
    """
    Analyse one or more images of an industrial piece.
    Returns OK / REVISAR / NOK with full diagnostic.

    Limits:
      - 1 to 3 images per request.
      - Max MAX_IMAGE_BYTES per image (default 10 MB).
      - JPEG, PNG, GIF, WebP only.
    """
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="API Key de Anthropic no configurada.")

    if len(images) == 0:
        raise HTTPException(status_code=400, detail="Se requiere al menos una imagen.")

    if len(images) > 3:
        raise HTTPException(status_code=400, detail="Máximo 3 imágenes por análisis.")

    empresa_id = usuario.get("empresa_id")

    # Validate and read all images before calling the AI
    validated: list[tuple[bytes, str]] = []
    for img in images:
        raw = await validate_image(img)
        # Use magic-byte-detected type; fall back to declared content_type
        declared = img.content_type or "image/jpeg"
        media_type = declared if declared in ALLOWED_MIME_TYPES else "image/jpeg"
        validated.append((raw, media_type))

    # Known defects for this piece type (client customisation)
    defectos_conocidos = obtener_defectos_tipo(tipo_pieza, empresa_id)
    system_prompt = construir_prompt(tipo_pieza, defectos_conocidos)

    # Build Claude Vision content
    content = [
        {
            "type": "text",
            "text": (
                f"Inspecciona esta pieza de tipo '{tipo_pieza}'. "
                f"Se proporcionan {len(validated)} imagen(es). "
                f"Analiza todos los defectos visibles con criterio industrial estricto."
            ),
        }
    ]
    for raw, media_type in validated:
        b64 = base64.standard_b64encode(raw).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })

    # Call Claude Vision
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        raw_text = response.content[0].text.strip()
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        resultado_ia = json.loads(clean_text)

    except json.JSONDecodeError:
        logger.error("Claude response was not valid JSON: %s", raw_text[:200])
        raise HTTPException(status_code=500, detail="Error al parsear respuesta de la IA.")
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error en análisis: {exc}")

    # Validate and normalise result fields
    resultado = resultado_ia.get("resultado", "REVISAR")
    if resultado not in {"OK", "REVISAR", "NOK"}:
        resultado = "REVISAR"

    confianza = int(resultado_ia.get("confianza", 70))
    defecto   = resultado_ia.get("defecto")
    zona      = resultado_ia.get("zona")
    accion    = resultado_ia.get("accion", "Revisar manualmente.")
    resumen   = resultado_ia.get("resumen", "Análisis completado.")

    # Persist
    analisis_id = registrar_analisis(
        empresa_id=empresa_id, tipo_pieza=tipo_pieza,
        resultado=resultado, confianza=confianza,
        defecto=defecto, zona=zona, accion=accion,
        resumen=resumen, num_imagenes=len(validated),
    )

    logger.info(
        "Analysis id=%s empresa=%s tipo=%s resultado=%s confianza=%s",
        analisis_id, empresa_id, tipo_pieza, resultado, confianza,
    )

    return {
        "analisis_id":  analisis_id,
        "tipo_pieza":   tipo_pieza,
        "resultado":    resultado,
        "confianza":    confianza,
        "defecto":      defecto,
        "zona":         zona,
        "accion":       accion,
        "resumen":      resumen,
        "num_imagenes": len(validated),
        "modelo":       "claude-sonnet-4-6",
    }


@app.post("/iqi/verify")
def verify(
    req: VerificacionRequest,
    usuario: dict = Depends(get_usuario_actual),
):
    """
    Save the operator's verification of an analysis.
    Generates training data for future model improvement.
    """
    empresa_id    = usuario.get("empresa_id")
    nombre_usuario = usuario.get("nombre", "")

    ok = registrar_verificacion(
        analisis_id       = req.analisis_id,
        resultado_ia      = req.resultado_ia,
        resultado_operario= req.resultado_operario,
        empresa_id        = empresa_id,
        usuario_nombre    = nombre_usuario,
    )

    if not ok:
        raise HTTPException(status_code=500, detail="Error al guardar la verificación.")

    concordancia = (req.resultado_ia == req.resultado_operario)
    return {
        "ok":          True,
        "analisis_id": req.analisis_id,
        "concordancia": concordancia,
        "mensaje":     "Verificación guardada correctamente.",
    }


@app.get("/iqi/history")
def history(
    limite: int = 50,
    usuario: dict = Depends(get_usuario_actual),
):
    """Return analysis history for the user's company."""
    empresa_id = usuario.get("empresa_id")
    es_admin   = usuario.get("rol") == "admin"

    filas = obtener_historial_iqi(
        empresa_id=None if es_admin else empresa_id,
        limite=limite,
    )

    return [
        {
            "id":           f[0],
            "timestamp":    f[1],
            "tipo_pieza":   f[2],
            "resultado":    f[3],
            "confianza":    f[4],
            "defecto":      f[5],
            "accion":       f[6],
            "num_imagenes": f[7],
            "empresa":      f[8],
        }
        for f in filas
    ]


@app.get("/iqi/stats")
def stats(usuario: dict = Depends(get_usuario_actual)):
    """Return IQI statistics for the user's company."""
    empresa_id = usuario.get("empresa_id")
    es_admin   = usuario.get("rol") == "admin"
    return obtener_stats_iqi(empresa_id=None if es_admin else empresa_id)


@app.get("/iqi/tipos")
def tipos(usuario: dict = Depends(get_usuario_actual)):
    """Return piece types configured for the user's company."""
    empresa_id = usuario.get("empresa_id")
    filas = obtener_tipos_pieza(empresa_id)
    return [
        {
            "id":          f[0],
            "nombre":      f[1],
            "descripcion": f[2],
            "defectos":    json.loads(f[3]) if f[3] else [],
        }
        for f in filas
    ]


@app.post("/iqi/tipos")
def nuevo_tipo(
    req: TipoPiezaRequest,
    usuario: dict = Depends(get_usuario_actual),
):
    """Create a new piece type (admin or company user only)."""
    empresa_id = usuario.get("empresa_id")
    id_nuevo = crear_tipo_pieza(
        nombre=req.nombre,
        descripcion=req.descripcion,
        defectos=req.defectos,
        empresa_id=empresa_id,
    )
    if not id_nuevo:
        raise HTTPException(status_code=500, detail="Error al crear el tipo de pieza.")
    return {"ok": True, "id": id_nuevo, "nombre": req.nombre}
