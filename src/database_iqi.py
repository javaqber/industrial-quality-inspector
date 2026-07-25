import os
import json
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    """Devuelve una conexión a PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)


# ─── INICIALIZACIÓN ───────────────────────────────────────────────────────────

def init_iqi_db():
    """Crea las tablas de IQI si no existen."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_pieza_iqi (
            id              SERIAL PRIMARY KEY,
            nombre          TEXT NOT NULL,
            descripcion     TEXT,
            defectos        TEXT DEFAULT '[]',
            empresa_id      INTEGER REFERENCES empresas(id),
            activo          BOOLEAN DEFAULT TRUE,
            fecha_registro  TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analisis_iqi (
            id              SERIAL PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            empresa_id      INTEGER REFERENCES empresas(id),
            tipo_pieza      TEXT NOT NULL,
            resultado       TEXT NOT NULL,
            confianza       INTEGER NOT NULL,
            defecto         TEXT,
            zona            TEXT,
            accion          TEXT,
            resumen         TEXT,
            num_imagenes    INTEGER DEFAULT 1,
            modelo_usado    TEXT DEFAULT 'claude-sonnet-4-6'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS verificaciones_iqi (
            id                  SERIAL PRIMARY KEY,
            analisis_id         INTEGER REFERENCES analisis_iqi(id),
            timestamp           TEXT NOT NULL,
            resultado_ia        TEXT NOT NULL,
            resultado_operario  TEXT NOT NULL,
            concordancia        BOOLEAN NOT NULL,
            empresa_id          INTEGER REFERENCES empresas(id),
            usuario_nombre      TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# ─── TIPOS DE PIEZA ────────────────────────────────────────────────────────────

def obtener_tipos_pieza(empresa_id=None):
    """Devuelve los tipos de pieza disponibles para una empresa."""
    conn = get_conn()
    cur = conn.cursor()
    if empresa_id:
        cur.execute("""
            SELECT id, nombre, descripcion, defectos
            FROM tipos_pieza_iqi
            WHERE activo = TRUE AND (empresa_id = %s OR empresa_id IS NULL)
            ORDER BY nombre
        """, (empresa_id,))
    else:
        cur.execute("""
            SELECT id, nombre, descripcion, defectos
            FROM tipos_pieza_iqi
            WHERE activo = TRUE
            ORDER BY nombre
        """)
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return filas


def crear_tipo_pieza(nombre, descripcion, defectos, empresa_id=None):
    """Registra un nuevo tipo de pieza."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tipos_pieza_iqi
            (nombre, descripcion, defectos, empresa_id, fecha_registro)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (
            nombre, descripcion,
            json.dumps(defectos if isinstance(defectos, list) else []),
            empresa_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        id_nuevo = cur.fetchone()[0]
        conn.commit()
        return id_nuevo
    except Exception as e:
        conn.rollback()
        print(f"Error creando tipo pieza: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def obtener_defectos_tipo(nombre_tipo, empresa_id=None):
    """Devuelve la lista de defectos conocidos para un tipo de pieza."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if empresa_id:
            cur.execute("""
                SELECT defectos FROM tipos_pieza_iqi
                WHERE nombre = %s AND activo = TRUE
                AND (empresa_id = %s OR empresa_id IS NULL)
                LIMIT 1
            """, (nombre_tipo, empresa_id))
        else:
            cur.execute("""
                SELECT defectos FROM tipos_pieza_iqi
                WHERE nombre = %s AND activo = TRUE
                LIMIT 1
            """, (nombre_tipo,))
        fila = cur.fetchone()
        if fila and fila[0]:
            return json.loads(fila[0])
        return []
    except Exception:
        return []
    finally:
        cur.close()
        conn.close()


# ─── ANÁLISIS ─────────────────────────────────────────────────────────────────

def registrar_analisis(empresa_id, tipo_pieza, resultado, confianza,
                       defecto, zona, accion, resumen, num_imagenes=1):
    """Guarda un análisis en la base de datos. Devuelve el ID."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO analisis_iqi
            (timestamp, empresa_id, tipo_pieza, resultado, confianza,
             defecto, zona, accion, resumen, num_imagenes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            empresa_id, tipo_pieza, resultado, confianza,
            defecto, zona, accion, resumen, num_imagenes
        ))
        id_nuevo = cur.fetchone()[0]
        conn.commit()
        return id_nuevo
    except Exception as e:
        conn.rollback()
        print(f"Error registrando análisis: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def obtener_historial_iqi(empresa_id=None, limite=50):
    """Devuelve el historial de análisis. None = todos (admin)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if empresa_id is None:
            cur.execute("""
                SELECT a.id, a.timestamp, a.tipo_pieza, a.resultado,
                       a.confianza, a.defecto, a.accion, a.num_imagenes,
                       e.nombre as empresa
                FROM analisis_iqi a
                LEFT JOIN empresas e ON a.empresa_id = e.id
                ORDER BY a.id DESC LIMIT %s
            """, (limite,))
        else:
            cur.execute("""
                SELECT a.id, a.timestamp, a.tipo_pieza, a.resultado,
                       a.confianza, a.defecto, a.accion, a.num_imagenes,
                       e.nombre as empresa
                FROM analisis_iqi a
                LEFT JOIN empresas e ON a.empresa_id = e.id
                WHERE a.empresa_id = %s
                ORDER BY a.id DESC LIMIT %s
            """, (empresa_id, limite))
        return cur.fetchall()
    except Exception as e:
        print(f"Error obteniendo historial: {e}")
        return []
    finally:
        cur.close()
        conn.close()


# ─── VERIFICACIONES ───────────────────────────────────────────────────────────

def registrar_verificacion(analisis_id, resultado_ia, resultado_operario,
                           empresa_id, usuario_nombre=""):
    """Guarda la verificación del operario sobre un análisis."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        concordancia = (resultado_ia == resultado_operario)
        cur.execute("""
            INSERT INTO verificaciones_iqi
            (analisis_id, timestamp, resultado_ia, resultado_operario,
             concordancia, empresa_id, usuario_nombre)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            analisis_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            resultado_ia, resultado_operario,
            concordancia, empresa_id, usuario_nombre
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error registrando verificación: {e}")
        return False
    finally:
        cur.close()
        conn.close()


# ─── ESTADÍSTICAS ─────────────────────────────────────────────────────────────

def obtener_stats_iqi(empresa_id=None):
    """Devuelve estadísticas del sistema IQI."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        filtro = "WHERE empresa_id = %s" if empresa_id else ""
        params = (empresa_id,) if empresa_id else ()

        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN resultado = 'OK' THEN 1 ELSE 0 END) as ok,
                SUM(CASE WHEN resultado = 'REVISAR' THEN 1 ELSE 0 END) as revisar,
                SUM(CASE WHEN resultado = 'NOK' THEN 1 ELSE 0 END) as nok,
                ROUND(AVG(confianza)) as confianza_media
            FROM analisis_iqi {filtro}
        """, params)
        fila = cur.fetchone()
        total, ok, revisar, nok, confianza_media = fila if fila else (
            0, 0, 0, 0, 0)

        cur.execute(f"""
            SELECT COUNT(*) FROM verificaciones_iqi {filtro}
        """, params)
        verificaciones = cur.fetchone()[0] or 0

        cur.execute(f"""
            SELECT COUNT(*) FROM verificaciones_iqi
            {'WHERE empresa_id = %s AND' if empresa_id else 'WHERE'} concordancia = TRUE
        """, params)
        concordancias = cur.fetchone()[0] or 0

        return {
            "total_analisis": total or 0,
            "ok": ok or 0,
            "revisar": revisar or 0,
            "nok": nok or 0,
            "confianza_media": int(confianza_media) if confianza_media else 0,
            "verificaciones": verificaciones,
            "tasa_concordancia": round(concordancias / verificaciones * 100, 1) if verificaciones > 0 else 0
        }
    except Exception as e:
        print(f"Error obteniendo stats: {e}")
        return {"total_analisis": 0, "ok": 0, "revisar": 0, "nok": 0,
                "confianza_media": 0, "verificaciones": 0, "tasa_concordancia": 0}
    finally:
        cur.close()
        conn.close()

# ─── USUARIOS (compartido con AuraPredict) ───────────────────────────────────


def obtener_usuario_por_email(email):
    """Obtiene los datos de un usuario para login."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, password_hash, nombre, rol, empresa_id, activo "
            "FROM usuarios WHERE email = %s",
            (email,)
        )
        return cur.fetchone()
    except Exception as e:
        print(f"Error obteniendo usuario: {e}")
        return None
    finally:
        cur.close()
        conn.close()


# ─── AUTOEJECUCIÓN ────────────────────────────────────────────────────────────
init_iqi_db()
