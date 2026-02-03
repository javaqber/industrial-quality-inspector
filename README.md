# 🛡️ Industrial Quality Inspector AI (CV + FastAPI + Docker)

Este proyecto es un sistema de **Visión Artificial end-to-end** para el control de calidad en entornos de Industria 4.0. Utiliza Deep Learning para detectar defectos en superficies de acero y expone la inteligencia a través de una API REST.

Todo el entorno está contenerizado con **Docker**, asegurando un despliegue ligero (CPU-only) y reproducible en cualquier servidor de planta.

![Logo del Proyecto](assets/logo_IndustrialQI.png)

## 🏗️ Arquitectura

El sistema consta de un flujo de trabajo optimizado para inferencia en producción:

1.  **AI Core (YOLOv8):**
    - Modelo de clasificación entrenado mediante _Transfer Learning_ sobre el dataset industrial **NEU-CLS**.
    - Capaz de diferenciar entre 6 tipos de defectos críticos (Scratches, Patches, Inclusions, etc.) con alta precisión.
2.  **API Service (FastAPI):**
    - Interfaz REST de alto rendimiento que recibe imágenes de superficies metálicas.
    - Procesa la imagen, ejecuta la inferencia en el modelo y devuelve una decisión de negocio en formato JSON (Tipo de defecto, Confianza % y Acción requerida: OK/NOK).
    - Incluye documentación interactiva automática (Swagger UI).
3.  **Contenedorización (Docker):**
    - Empaquetado en una imagen Linux ligera (basada en Python Slim).
    - Optimizado para ejecutarse sin necesidad de GPU dedicada, utilizando versiones ligeras de PyTorch y herramientas headless.

## 🚀 Tecnologías

- **Lenguaje:** Python 3.10
- **IA / Computer Vision:** Ultralytics YOLOv8, PyTorch (CPU), OpenCV-headless
- **Backend:** FastAPI, Uvicorn
- **Contenedores:** Docker

## 🛠️ Instalación y Uso

### Prerrequisitos

- Tener [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y corriendo.

### Pasos

1.  Clonar el repositorio:

    ```bash
    git clone https://github.com/javaqber/industrial-quality-inspector.git
    cd industrial_quality_inspector
    ```

2.  Construir la imagen Docker:

    ```bash
    docker build -t inspector-calidad .
    ```

3.  Arrancar el servicio:

    ```bash
    docker run -p 8000:8000 inspector-calidad
    ```

4.  Acceder a la API y probarla:
    - Abre tu navegador en: `http://localhost:8501/docs`
    - Usa el endpoint `POST /predict` para subir una imagen de prueba y ver el resultado del análisis.

5.  Detener el sistema:
    - Pulsa `Ctrl + C` en la terminal.

## 📊 Previsualización del Flujo

El sistema está diseñado para recibir una imagen cruda y devolver una decisión accionable en milisegundos.

**Input (Imagen de ejemplo):**
_(Puedes poner aquí una imagen pequeña de un defecto de ejemplo)_

**Output (Respuesta JSON de la API):**

```json
{
  "filename": "pieza_test_01.jpg",
  "defect_type": "Scratches",
  "confidence": "99.8%",
  "action_required": "DESCARTAR PIEZA"
}
```
