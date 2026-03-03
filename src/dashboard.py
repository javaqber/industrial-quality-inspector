import streamlit as st
from ultralytics import YOLO  # Se importa la IA directamente al dashboard
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="IQI - AI Inspector",
                   page_icon="🏭", layout="centered")

# --- CARGA DEL MODELO DE IA ---
# cache_resource asegura que el modelo pesado se cargue solo 1 vez en memoria


@st.cache_resource(show_spinner=False)
def load_model():
    # Cargamos el modelo IA en la raiz del proyecto
    return YOLO("best_aluminio.pt")


try:
    model = load_model()
except Exception as e:
    st.error(
        f"⚠️ Error al cargar el modelo de IA. Verifica que el archivo .pt está en la carpeta: {e}")

# --- CSS PERSONALIZADO ---
st.markdown("""
    <style>
    /* Importamos fuente estilo industrial para el titulo */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700&display=swap');
    
    /* --- ESTILOS DE LA INTERFAZ (Botones y Cajas) --- */
    .stButton>button {
        background-color: #0e4b75;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        width: 100%;
        height: 50px;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #1a73e8;
        border-color: #1a73e8;
    }
    .result-box {
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin-top: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .defect { background-color: #ffeef0; border: 2px solid #ff4d4f; color: #a8071a; }
    .ok { background-color: #f6ffed; border: 2px solid #52c41a; color: #237804; }
    .metric-text { font-size: 1.2rem; margin: 5px 0; }
    
    /* --- ESTILOS DEL TÍTULO --- */
    .titulo-custom {
        font-family: 'Orbitron', sans-serif;
        text-align: center;
        font-size: 2.2rem;
        margin-top: -10px;
        margin-bottom: 5px;
    }
    .titulo-custom .industrial { color: #1a7bb7; }
    .titulo-custom .quality { color: #58595b; }
    .subtitulo-custom {
        text-align: center;
        font-size: 1.1rem;
        color: #666666;
        margin-bottom: 30px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. LOGO CENTRADO ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    try:
        st.image("assets/logo_IQI_trans.png", use_container_width=True)
    except:
        st.error("⚠️ No se encuentra el logo en 'assets/logo_IQI_trans.png'")

# --- 2. TÍTULO Y SUBTÍTULO CENTRADOS ---
st.markdown("""
    <h1 class="titulo-custom">
        <span class="industrial">INDUSTRIAL</span> <span class="quality">QUALITY INSPECTOR</span>
    </h1>
    <p class="subtitulo-custom">Sistema de Visión Artificial para perfiles de aluminio.</p>
""", unsafe_allow_html=True)

st.markdown("---")

# --- 3. SUBIDA DE IMAGEN ---
uploaded_file = st.file_uploader(
    "📸 Sube una foto del perfil extruido", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)

    # Metemos la imagen en una columna central para que no sea gigante
    col_img1, col_img2, col_img3 = st.columns([1, 2, 1])
    with col_img2:
        st.image(image, caption="Muestra a analizar", use_container_width=True)

    # --- 4. BOTÓN E INFERENCIA DIRECTA ---
    if st.button("🔍 Iniciar Análisis con IA"):
        with st.spinner("🧠 Analizando la imagen localmente..."):
            try:
                resultados = model(image)
                result = resultados[0]

                # Extraemos los datos de clasificación
                if hasattr(result, 'probs') and result.probs is not None:
                    class_id = result.probs.top1
                    confianza = result.probs.top1conf.item()
                    defect_detected = result.names[class_id]
                    confidence_str = f"{confianza * 100:.2f}%"

                    #  EVALUAMOS SI ES DEFECTUOSA O SANA
                    # Asegúrate de que "clean_sample" es el nombre de la clase buena en YOLO
                    if defect_detected == "clean_sample" or defect_detected == "ok":
                        is_defective = False
                        action_required = "APROBAR PIEZA"
                    else:
                        is_defective = True
                        action_required = "DESCARTAR / REVISAR"
                else:
                    is_defective = False
                    defect_detected = "Error de lectura"
                    confidence_str = "0%"
                    action_required = "REPETIR FOTO"

                # --- 5. MOSTRAR RESULTADOS VISUALES ---
                if is_defective:
                    st.markdown(f"""
                    <div class="result-box defect">
                        <h2 style="color: #a8071a;">❌ DEFECTO DETECTADO</h2>
                        <p class="metric-text"><strong>Categoría:</strong> {defect_detected.upper().replace('_', ' ')}</p>
                        <p class="metric-text"><strong>Confianza IA:</strong> {confidence_str}</p>
                        <hr>
                        <h3 style="color: #a8071a;">ACCIÓN: {action_required}</h3>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="result-box ok">
                        <h2 style="color: #237804;">✅ PIEZA APROBADA</h2>
                        <p class="metric-text"><strong>Categoría:</strong> {defect_detected.upper().replace('_', ' ')}</p>
                        <p class="metric-text"><strong>Confianza IA:</strong> {confidence_str}</p>
                        <hr>
                        <h3 style="color: #237804;">ACCIÓN: {action_required}</h3>
                    </div>
                    """, unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error durante el procesamiento: {e}")
