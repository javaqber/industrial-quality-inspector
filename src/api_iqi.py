from database_iqi import (
    obtener_tipos_pieza, crear_tipo_pieza, obtener_defectos_tipo,
    registrar_analisis, obtener_historial_iqi,
    registrar_verificacion, obtener_stats_iqi,
    obtener_usuario_por_email
)
from auth import verificar_token, verificar_password, crear_token
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional
import anthropic
import base64
import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))


load_dotenv(dotenv_path=os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '../.env'))
load_dotenv()


# ─── APP ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IQI — Industrial Quality Inspector API",
    description="API de inspección visual de calidad industrial con Claude Vision AI.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── AUTH ─────────────────────────────────────────────────────────────────────

security = HTTPBearer()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def get_usuario_actual(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Valida el JWT y devuelve el payload del usuario."""
    payload = verificar_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401, detail="Token inválido o expirado.")
    return payload


# ─── PROMPT DEL SISTEMA ───────────────────────────────────────────────────────

def construir_prompt(tipo_pieza: str, defectos_conocidos: list) -> str:
    """Construye el system prompt adaptado al tipo de pieza del cliente."""
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

STATIC_DIR = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '../static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "status": "IQI API activa",
        "version": "1.0.0",
        "modelo": "claude-sonnet-4-6"
    }


@app.get("/app")
def serve_app():
    """Sirve la PWA móvil."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="PWA no encontrada.")
    return FileResponse(index_path)


@app.post("/login")
def login(req: LoginRequest):
    """Login con email y password. Devuelve token JWT."""
    usuario = obtener_usuario_por_email(req.email)
    if not usuario:
        raise HTTPException(
            status_code=401, detail="Credenciales incorrectas.")

    id_u, email_u, password_hash, nombre, rol, empresa_id, activo = usuario

    if not activo:
        raise HTTPException(status_code=401, detail="Cuenta desactivada.")

    if not verificar_password(req.password, password_hash):
        raise HTTPException(
            status_code=401, detail="Credenciales incorrectas.")

    token = crear_token({
        "sub": email_u,
        "nombre": nombre,
        "rol": rol,
        "empresa_id": empresa_id
    })

    return {
        "access_token": token,
        "token_type":   "bearer",
        "nombre":       nombre,
        "rol":          rol,
        "empresa_id":   empresa_id
    }


@app.post("/iqi/analyze")
async def analyze(
    tipo_pieza: str = Form(...),
    images: List[UploadFile] = File(...),
    usuario: dict = Depends(get_usuario_actual)
):
    """
    Analiza una o varias imágenes de una pieza industrial.
    Devuelve resultado OK / REVISAR / NOK con diagnóstico completo.
    """
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500, detail="API Key de Anthropic no configurada.")

    if len(images) == 0:
        raise HTTPException(
            status_code=400, detail="Se requiere al menos una imagen.")

    if len(images) > 3:
        raise HTTPException(
            status_code=400, detail="Máximo 3 imágenes por análisis.")

    empresa_id = usuario.get("empresa_id")

    # Obtener defectos conocidos del tipo de pieza (personalización por cliente)
    defectos_conocidos = obtener_defectos_tipo(tipo_pieza, empresa_id)

    # Construir prompt adaptado
    system_prompt = construir_prompt(tipo_pieza, defectos_conocidos)

    # Preparar imágenes para Claude Vision
    content = [
        {
            "type": "text",
            "text": f"Inspecciona esta pieza de tipo '{tipo_pieza}'. "
                    f"Se proporcionan {len(images)} imagen(es). "
                    f"Analiza todos los defectos visibles con criterio industrial estricto."
        }
    ]

    for img in images:
        raw = await img.read()
        b64 = base64.standard_b64encode(raw).decode("utf-8")
        media_type = img.content_type or "image/jpeg"
        if media_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
            media_type = "image/jpeg"
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64
            }
        })

    # Llamada a Claude Vision
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": content}]
        )
        raw_text = response.content[0].text.strip()
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        resultado_ia = json.loads(clean_text)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500, detail="Error al parsear respuesta de la IA.")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error en análisis: {str(e)}")

    # Validar campos obligatorios
    resultado = resultado_ia.get("resultado", "REVISAR")
    if resultado not in ["OK", "REVISAR", "NOK"]:
        resultado = "REVISAR"

    confianza = int(resultado_ia.get("confianza", 70))
    defecto = resultado_ia.get("defecto")
    zona = resultado_ia.get("zona")
    accion = resultado_ia.get("accion", "Revisar manualmente.")
    resumen = resultado_ia.get("resumen", "Análisis completado.")

    # Guardar en base de datos
    analisis_id = registrar_analisis(
        empresa_id=empresa_id,
        tipo_pieza=tipo_pieza,
        resultado=resultado,
        confianza=confianza,
        defecto=defecto,
        zona=zona,
        accion=accion,
        resumen=resumen,
        num_imagenes=len(images)
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
        "num_imagenes": len(images),
        "modelo":       "claude-sonnet-4-6"
    }


@app.post("/iqi/verify")
def verify(
    req: VerificacionRequest,
    usuario: dict = Depends(get_usuario_actual)
):
    """
    Guarda la verificación del operario sobre un análisis previo.
    Genera datos de entrenamiento para mejorar el modelo a futuro.
    """
    empresa_id = usuario.get("empresa_id")
    nombre_usuario = usuario.get("nombre", "")

    ok = registrar_verificacion(
        analisis_id=req.analisis_id,
        resultado_ia=req.resultado_ia,
        resultado_operario=req.resultado_operario,
        empresa_id=empresa_id,
        usuario_nombre=nombre_usuario
    )

    if not ok:
        raise HTTPException(
            status_code=500, detail="Error al guardar la verificación.")

    concordancia = (req.resultado_ia == req.resultado_operario)
    return {
        "ok": True,
        "analisis_id": req.analisis_id,
        "concordancia": concordancia,
        "mensaje": "Verificación guardada correctamente."
    }


@app.get("/iqi/history")
def history(
    limite: int = 50,
    usuario: dict = Depends(get_usuario_actual)
):
    """Devuelve el historial de análisis de la empresa del usuario."""
    empresa_id = usuario.get("empresa_id")
    es_admin = usuario.get("rol") == "admin"

    filas = obtener_historial_iqi(
        empresa_id=None if es_admin else empresa_id,
        limite=limite
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
            "empresa":      f[8]
        }
        for f in filas
    ]


@app.get("/iqi/stats")
def stats(usuario: dict = Depends(get_usuario_actual)):
    """Devuelve estadísticas del sistema IQI para la empresa del usuario."""
    empresa_id = usuario.get("empresa_id")
    es_admin = usuario.get("rol") == "admin"
    return obtener_stats_iqi(empresa_id=None if es_admin else empresa_id)


@app.get("/iqi/tipos")
def tipos(usuario: dict = Depends(get_usuario_actual)):
    """Devuelve los tipos de pieza configurados para la empresa."""
    empresa_id = usuario.get("empresa_id")
    filas = obtener_tipos_pieza(empresa_id)
    return [
        {
            "id":          f[0],
            "nombre":      f[1],
            "descripcion": f[2],
            "defectos":    json.loads(f[3]) if f[3] else []
        }
        for f in filas
    ]


@app.post("/iqi/tipos")
def nuevo_tipo(
    req: TipoPiezaRequest,
    usuario: dict = Depends(get_usuario_actual)
):
    """Crea un nuevo tipo de pieza (solo admin o cliente de la empresa)."""
    empresa_id = usuario.get("empresa_id")
    id_nuevo = crear_tipo_pieza(
        nombre=req.nombre,
        descripcion=req.descripcion,
        defectos=req.defectos,
        empresa_id=empresa_id
    )
    if not id_nuevo:
        raise HTTPException(
            status_code=500, detail="Error al crear el tipo de pieza.")
    return {"ok": True, "id": id_nuevo, "nombre": req.nombre}
