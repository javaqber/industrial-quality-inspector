import os
import shutil
from fastapi import FastAPI, UploadFile, File
from ultralytics import YOLO

app = FastAPI(
    title="Industrial Quality Inspector - Aluminium Edition",
    description="API de IA para detección de defectos en extrusión de aluminio.",
    version="2.0.0",
    contact={
        "name": "Javier Vaquero - AI Engineer",
        "email": "jvaquero03@gmail.com"
    },
)

# --- 1. CARGAMOS EL CEREBRO DIRECTAMENTE ---
# Al poner solo el nombre, Python lo busca en la misma carpeta que main.py
MODEL_NAME = "best_aluminio.pt"

print(f"🔍 Cargando modelo: {MODEL_NAME}...")
try:
    model = YOLO(MODEL_NAME)
    print("✅ Modelo cargado y listo para trabajar.")
except Exception as e:
    print(
        f"❌ ERROR: No encuentro '{MODEL_NAME}'. Asegúrate de que está en la carpeta.")
    # Fallback por si acaso, aunque lo ideal es que falle si no está el bueno
    model = YOLO("yolov8n-cls.pt")


# --- 2. ENDPOINT DE INICIO ---
@app.get("/")
def home():
    return {"status": "online", "system": "Aluminium Inspector AI v2.0"}


# --- 3. ENDPOINT DE PREDICCIÓN ---
@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    # Guardamos la foto temporalmente
    temp_filename = f"temp_{file.filename}"
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Inferencia
        results = model.predict(temp_filename, conf=0.5)
        result = results[0]

        # Extraer datos
        class_id = result.probs.top1
        class_name = result.names[class_id]
        confidence = result.probs.top1conf.item()

        # --- LÓGICA DE NEGOCIO ---
        # En el dataset, la pieza buena se llama 'clean_sample'.
        # Cualquier otra cosa es un defecto.

        es_defectuoso = class_name != "clean_sample"

        accion = "APROBAR PIEZA"
        if es_defectuoso:
            accion = "DESCARTAR - REVISAR EXTRUSORA"

        # Si la confianza es baja (menos del 70%) - Se avisa al supervisor
        if confidence < 0.70:
            accion += " (DUDOSO - VERIFICAR MANUALMENTE)"

        return {
            "filename": file.filename,
            "material": "Aluminio",
            "defect_detected": class_name,
            "is_defective": es_defectuoso,
            "confidence": f"{confidence:.2%}",
            "action_required": accion
        }

    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
