from ultralytics import YOLO

# 1. Cargamos el modelo
# El sufijo '-cls' significa CLASSIFICATION.
# Buscamos etiquetas.
print("Cargando modelo de Clasificación...")
model = YOLO('yolov8n-cls.pt')

# 2. Entrenamos
# data: La ruta a la carpeta de datos a aprender.
# epochs: Cuántas veces repasará el temario.
# imgsz: Tamaño de la foto (640x640 es estándar).
print("Iniciando entrenamiento...")

results = model.train(
    data='datasets/alum_cls',
    epochs=20,  # Entre 20 - 50 epochs
    imgsz=224,  # Resolución Estandar de industria
    name='test_calidad_aluminio'
)

print("¡Entrenamiento finalizado!")
