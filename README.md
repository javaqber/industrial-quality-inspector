# 🔍 IQI Aluminium — Industrial Quality Inspector

Sistema de inspección visual de calidad industrial para operarios a pie de máquina.

**Flujo:** El operario fotografía una pieza → la IA analiza → devuelve OK / REVISAR / NOK → el operario puede validar o corregir → todo queda registrado para trazabilidad.

![Logo IQI](assets/logo_IQI_trans.png)

---

## Arquitectura

```
Móvil (PWA — static/index.html)
        ↓ HTTPS
FastAPI (src/api_iqi.py)
        ↓ Anthropic SDK
Claude Vision AI (claude-sonnet-4-6)
        ↓
PostgreSQL (Supabase — compartido con AuraPredict)
```

## Stack técnico

| Componente | Tecnología |
|---|---|
| Backend | FastAPI + Uvicorn (Python 3.12) |
| IA | Claude Vision (Anthropic claude-sonnet-4-6) |
| Frontend | PWA single-file (`static/index.html`) |
| Base de datos | PostgreSQL via psycopg2 |
| Auth | JWT (python-jose + bcrypt) |
| Deploy | Docker |

## Estructura del proyecto

```
iqi/
├── src/
│   ├── api_iqi.py        ← API principal (FastAPI)
│   ├── auth.py           ← JWT auth
│   └── database_iqi.py   ← Capa PostgreSQL
├── static/
│   └── index.html        ← PWA móvil (autocontenida)
├── assets/               ← Logos
├── scripts/
│   └── legacy_yolo/      ← Implementación YOLO original (archivada)
├── Dockerfile
├── requirements.txt
└── .env.example          ← Variables de entorno necesarias
```

## Variables de entorno

Crea un archivo `.env` en la raíz:

```env
# PostgreSQL (compartida con AuraPredict)
DATABASE_URL=postgresql://usuario:password@host:5432/database

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# JWT
SECRET_KEY=clave_secreta_larga_y_aleatoria

# CORS (orígenes permitidos separados por coma)
CORS_ORIGINS=http://localhost:8000,https://tudominio.com

# Límite de tamaño de imagen (bytes, default 10MB)
MAX_IMAGE_BYTES=10485760
```

## Arranque local

```bash
# 1. Instalar dependencias
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurar entorno
cp .env.example .env
# Editar .env con tus valores reales

# 3. Arrancar API
uvicorn src.api_iqi:app --reload --port 8000

# 4. Acceder a la PWA
# http://localhost:8000/app
# Documentación: http://localhost:8000/docs
```

## Arranque con Docker

```bash
# Construir imagen
docker build -t iqi-aluminium .

# Arrancar contenedor
docker run -p 8000:8000 --env-file .env iqi-aluminium

# Acceder
# PWA:  http://localhost:8000/app
# Docs: http://localhost:8000/docs
```

## Endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/login` | Login → JWT |
| POST | `/iqi/analyze` | Analizar imagen(es) con IA |
| POST | `/iqi/verify` | Verificar/corregir resultado |
| GET | `/iqi/history` | Historial de análisis |
| GET | `/iqi/stats` | Estadísticas por empresa |
| GET | `/iqi/tipos` | Tipos de pieza configurados |
| POST | `/iqi/tipos` | Crear tipo de pieza |

## Tablas de base de datos

IQI utiliza la misma instancia PostgreSQL que AuraPredict.

**Compartidas:**
- `empresas` — clientes/tenants
- `usuarios` — usuarios con roles

**Específicas de IQI:**
- `tipos_pieza_iqi` — tipos de pieza configurados por empresa
- `analisis_iqi` — registro de cada inspección
- `verificaciones_iqi` — correcciones del operario (futuro ground truth para ML)

## Implementación YOLO (archivada)

La implementación original basada en YOLOv8 está conservada en `scripts/legacy_yolo/`.
No se usa en producción. Ver `scripts/legacy_yolo/README.md` para más información.

El modelo entrenado `best_aluminio.pt` se conserva como base para integración futura
como fallback offline o punto de partida para modelos supervisados.

## Roadmap pendiente

- [ ] Almacenamiento de imágenes en Supabase Storage (trazabilidad completa)
- [ ] Migración de timestamps TEXT → TIMESTAMPTZ
- [ ] Token de refresco automático
- [ ] Tipos de pieza dinámicos en la PWA (carga desde `/iqi/tipos`)
- [ ] Rate limiting por empresa en `/iqi/analyze`
- [ ] PWA manifest.json (instalable en móvil)
