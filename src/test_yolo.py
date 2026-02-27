from ultralytics import YOLO

# 1. Cargamos el modelo.
# 'yolov8n.pt' es un modelo pre-entrenado por expertos.
# La 'n' significa Nano (ideal para pruebas).
print("Cargando modelo...")
model = YOLO("yolov8n.pt")

# 2. Hacemos la predicción
# Se pasa una URL de una imagen cualquiera para probar.
# 'conf=0.5' significa: "Solo dime lo que veas si estás un 50% seguro".
print("Analizando imagen...")
results = model.predict(
    "https://ultralytics.com/images/bus.jpg", save=True, conf=0.5)

# 3. Explicación de results
# La variable 'results' es una lista con todo lo que ha visto
print("¡Análisis completado!")
