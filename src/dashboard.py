import streamlit as st
import requests
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="IQI - AI Inspector",
                   page_icon="🏭", layout="centered")

# --- DESPIERTA LA API ---


@st.cache_resource(show_spinner=False)
def despertar_api():
    try:
        # Añadido el carnet de identidad para evitar bloqueos
        headers = {"User-Agent": "IQI-Dashboard/1.0"}
        # Aquí enviamos el 'headers' en la petición
        requests.get(
            "https://industrial-quality-inspector.onrender.com/docs", headers=headers, timeout=60)
        return True
    except:
        return False


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
    .titulo-custom .industrial {
        color: #1a7bb7; /* El azul logo */
    }
    .titulo-custom .quality {
        color: #58595b; /* El gris oscuro logo */
    }
    .subtitulo-custom {
        text-align: center;
        font-size: 1.1rem;
        color: #666666;
        margin-bottom: 30px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

API_URL = "https://industrial-quality-inspector.onrender.com"

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

# --- 3. MENSAJE EFÍMERO (TOAST) ---
with st.spinner("📡 Conectando con los servidores de Inteligencia Artificial..."):
    is_awake = despertar_api()

if is_awake:
    st.toast("✅ Sistema en línea y calibrado. Listo para inspección.", icon="🚀")
else:
    st.toast("⚠️ La conexión va lenta, pero puedes intentar subir la pieza.", icon="⏳")

st.markdown("---")

# --- 4. SUBIDA DE IMAGEN MÁS PEQUEÑA ---
uploaded_file = st.file_uploader(
    "📸 Sube una foto del perfil extruido", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)

    # Metemos la imagen en una columna central para que no sea gigante
    col_img1, col_img2, col_img3 = st.columns([1, 2, 1])
    with col_img2:
        st.image(image, caption="Muestra a analizar", use_container_width=True)

   # Botón de Inferencia
    if st.button("🔍 Iniciar Análisis con IA"):
        # Actualizamos el mensaje para que el usuario no se asuste si tarda
        with st.spinner("🧠 Despertando servidores y procesando imagen (la primera vez puede tardar hasta 1 minuto)..."):
            img_bytes = uploaded_file.getvalue()

            headers_analysis = {"User-Agent": "IQI-Dashboard/1.0"}

            # --- LÓGICA DE REINTENTOS AMPLIADA ---
            import time  # Por si no lo tenías arriba
            max_intentos = 6
            exito = False

            for intento in range(max_intentos):
                try:
                    files = {"file": (uploaded_file.name,
                                      img_bytes, uploaded_file.type)}

                    response = requests.post(
                        f"{API_URL}/predict", files=files, headers=headers_analysis, timeout=60)

                    if response.status_code == 200:
                        data = response.json()
                        exito = True

                        # Mostrar Resultados Visuales
                        if data["is_defective"]:
                            st.markdown(f"""
                            <div class="result-box defect">
                                <h2 style="color: #a8071a;">❌ DEFECTO DETECTADO</h2>
                                <p class="metric-text"><strong>Categoría:</strong> {data['defect_detected'].upper().replace('_', ' ')}</p>
                                <p class="metric-text"><strong>Confianza IA:</strong> {data['confidence']}</p>
                                <hr>
                                <h3 style="color: #a8071a;">ACCIÓN: {data['action_required']}</h3>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="result-box ok">
                                <h2 style="color: #237804;">✅ PIEZA APROBADA</h2>
                                <p class="metric-text"><strong>Categoría:</strong> {data['defect_detected'].upper().replace('_', ' ')}</p>
                                <p class="metric-text"><strong>Confianza IA:</strong> {data['confidence']}</p>
                                <hr>
                                <h3 style="color: #237804;">ACCIÓN: {data['action_required']}</h3>
                            </div>
                            """, unsafe_allow_html=True)
                        break  # ¡Conseguido! Salimos del bucle

                    # Atrapamos tanto el 429 (Bloqueo) como el 503/502 (Arrancando)
                    elif response.status_code in [429, 502, 503]:
                        if intento < max_intentos - 1:
                            # Esperamos 15 segundos y volvemos a golpear la puerta
                            time.sleep(15)
                            continue
                        else:
                            st.error(
                                "⚠️ El servidor de la API está tardando demasiado en arrancar. Por favor, recarga la página en unos segundos.")
                    else:
                        st.error(f"Error del servidor: {response.status_code}")
                        break

                except Exception as e:
                    if intento < max_intentos - 1:
                        time.sleep(15)
                        continue
                    else:
                        st.error(
                            f"Error de conexión con la API tras varios intentos: {e}")
