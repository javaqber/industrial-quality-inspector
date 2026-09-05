# ─── IQI Aluminium — Production Dockerfile (Fase 0B) ───────────────────────
#
# Image: python:3.12-slim  (matches runtime.txt)
# App:   src/api_iqi.py    (Claude Vision + PostgreSQL)
#
# Build:  docker build -t iqi-aluminium .
# Run:    docker run -p 8000:8000 --env-file .env iqi-aluminium
# Health: curl http://localhost:8000/

FROM python:3.12-slim

WORKDIR /app

# System libraries: only what psycopg2-binary actually needs on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and static files
COPY src/     ./src/
COPY static/  ./static/
COPY assets/  ./assets/

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Entrypoint: IQI Claude Vision API
CMD ["uvicorn", "src.api_iqi:app", "--host", "0.0.0.0", "--port", "8000"]
