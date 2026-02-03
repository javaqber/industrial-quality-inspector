# 1. IMAGEN BASE
FROM python:3.10-slim

# 2. DIRECTORIO DE TRABAJO
WORKDIR /app

# 3. INSTALAR LIBRERÍAS DE SISTEMA
# --- CORRECCIÓN AQUÍ ---
# Hemos cambiado 'libgl1-mesa-glx' por 'libgl1' que es el nombre moderno
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 4. INSTALAR DEPENDENCIAS PYTHON
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. COPIAR CÓDIGO
COPY . .

# 6. EXPONER PUERTO Y ARRANCAR
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]