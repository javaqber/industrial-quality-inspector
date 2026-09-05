"""
IQI — Database layer (Fase 0B)
================================
PostgreSQL CRUD for IQI Aluminium.

Shared tables with AuraPredict: empresas, usuarios
IQI-specific tables: tipos_pieza_iqi, analisis_iqi, verificaciones_iqi

Changes from Fase 0B:
  - init_iqi_db() is now EXPLICIT — no longer called at import time.
    Call it manually at app startup (from api_iqi.py lifespan event).
  - SQL injection fixed in obtener_stats_iqi: no more f-string SQL.
  - All functions use parameterised queries only.

PENDING (next phase):
  - timestamps should migrate from TEXT → TIMESTAMPTZ for proper date filtering.
    Current: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    Target:  datetime.now(timezone.utc)  with TIMESTAMPTZ columns.
"""

import os
import json
import logging
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

DATABASE_URL = os.getenv("DATABASE_URL")

logger = logging.getLogger(__name__)


def get_conn():
    """Return a PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


# ─── INITIALISATION ───────────────────────────────────────────────────────────

def init_iqi_db():
    """
    Create IQI tables if they do not exist.

    MUST be called explicitly at application startup.
    NOT called at import time — callers control when the DB connection happens.
    """
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
    # NOTE: timestamp is TEXT for backward-compatibility.
    # Next phase migration: ALTER TABLE analisis_iqi ALTER COLUMN timestamp TYPE TIMESTAMPTZ

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
    logger.info("IQI database tables verified/created.")


# ─── TIPOS DE PIEZA ────────────────────────────────────────────────────────────

def obtener_tipos_pieza(empresa_id=None):
    """Return active piece types for a company (or all if empresa_id is None)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
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
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def crear_tipo_pieza(nombre, descripcion, defectos, empresa_id=None):
    """Register a new piece type. Returns new id or None."""
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
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        id_nuevo = cur.fetchone()[0]
        conn.commit()
        return id_nuevo
    except Exception as exc:
        conn.rollback()
        logger.error("Error creating piece type: %s", exc)
        return None
    finally:
        cur.close()
        conn.close()


def obtener_defectos_tipo(nombre_tipo, empresa_id=None):
    """Return the known defect list for a piece type name."""
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
    """Save an analysis to the database. Returns the new id."""
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
            defecto, zona, accion, resumen, num_imagenes,
        ))
        id_nuevo = cur.fetchone()[0]
        conn.commit()
        return id_nuevo
    except Exception as exc:
        conn.rollback()
        logger.error("Error registering analysis: %s", exc)
        return None
    finally:
        cur.close()
        conn.close()


def obtener_historial_iqi(empresa_id=None, limite=50):
    """Return analysis history. empresa_id=None returns all (admin only)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if empresa_id is None:
            cur.execute("""
                SELECT a.id, a.timestamp, a.tipo_pieza, a.resultado,
                       a.confianza, a.defecto, a.accion, a.num_imagenes,
                       e.nombre AS empresa
                FROM analisis_iqi a
                LEFT JOIN empresas e ON a.empresa_id = e.id
                ORDER BY a.id DESC LIMIT %s
            """, (limite,))
        else:
            cur.execute("""
                SELECT a.id, a.timestamp, a.tipo_pieza, a.resultado,
                       a.confianza, a.defecto, a.accion, a.num_imagenes,
                       e.nombre AS empresa
                FROM analisis_iqi a
                LEFT JOIN empresas e ON a.empresa_id = e.id
                WHERE a.empresa_id = %s
                ORDER BY a.id DESC LIMIT %s
            """, (empresa_id, limite))
        return cur.fetchall()
    except Exception as exc:
        logger.error("Error fetching history: %s", exc)
        return []
    finally:
        cur.close()
        conn.close()


# ─── VERIFICACIONES ───────────────────────────────────────────────────────────

def registrar_verificacion(analisis_id, resultado_ia, resultado_operario,
                           empresa_id, usuario_nombre=""):
    """Save an operator verification for an analysis."""
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
            concordancia, empresa_id, usuario_nombre,
        ))
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Error registering verification: %s", exc)
        return False
    finally:
        cur.close()
        conn.close()


# ─── ESTADÍSTICAS ─────────────────────────────────────────────────────────────

def obtener_stats_iqi(empresa_id=None):
    """
    Return IQI statistics for a company.
    empresa_id=None returns global stats (admin).

    Security: all queries use parameterised placeholders — no f-string SQL.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # ── Totals per result ────────────────────────────────────────────────
        if empresa_id is not None:
            cur.execute("""
                SELECT
                    COUNT(*)                                                   AS total,
                    SUM(CASE WHEN resultado = 'OK'      THEN 1 ELSE 0 END)   AS ok,
                    SUM(CASE WHEN resultado = 'REVISAR' THEN 1 ELSE 0 END)   AS revisar,
                    SUM(CASE WHEN resultado = 'NOK'     THEN 1 ELSE 0 END)   AS nok,
                    ROUND(AVG(confianza))                                     AS confianza_media
                FROM analisis_iqi
                WHERE empresa_id = %s
            """, (empresa_id,))
        else:
            cur.execute("""
                SELECT
                    COUNT(*)                                                   AS total,
                    SUM(CASE WHEN resultado = 'OK'      THEN 1 ELSE 0 END)   AS ok,
                    SUM(CASE WHEN resultado = 'REVISAR' THEN 1 ELSE 0 END)   AS revisar,
                    SUM(CASE WHEN resultado = 'NOK'     THEN 1 ELSE 0 END)   AS nok,
                    ROUND(AVG(confianza))                                     AS confianza_media
                FROM analisis_iqi
            """)
        fila = cur.fetchone()
        total, ok, revisar, nok, confianza_media = fila if fila else (0, 0, 0, 0, 0)

        # ── Verification count ────────────────────────────────────────────────
        if empresa_id is not None:
            cur.execute(
                "SELECT COUNT(*) FROM verificaciones_iqi WHERE empresa_id = %s",
                (empresa_id,),
            )
        else:
            cur.execute("SELECT COUNT(*) FROM verificaciones_iqi")
        verificaciones = cur.fetchone()[0] or 0

        # ── Concordance count ─────────────────────────────────────────────────
        if empresa_id is not None:
            cur.execute("""
                SELECT COUNT(*) FROM verificaciones_iqi
                WHERE empresa_id = %s AND concordancia = TRUE
            """, (empresa_id,))
        else:
            cur.execute("""
                SELECT COUNT(*) FROM verificaciones_iqi
                WHERE concordancia = TRUE
            """)
        concordancias = cur.fetchone()[0] or 0

        return {
            "total_analisis":    total or 0,
            "ok":                ok or 0,
            "revisar":           revisar or 0,
            "nok":               nok or 0,
            "confianza_media":   int(confianza_media) if confianza_media else 0,
            "verificaciones":    verificaciones,
            "tasa_concordancia": round(concordancias / verificaciones * 100, 1)
                                 if verificaciones > 0 else 0,
        }
    except Exception as exc:
        logger.error("Error fetching stats: %s", exc)
        return {
            "total_analisis": 0, "ok": 0, "revisar": 0, "nok": 0,
            "confianza_media": 0, "verificaciones": 0, "tasa_concordancia": 0,
        }
    finally:
        cur.close()
        conn.close()


# ─── USUARIOS (shared with AuraPredict) ──────────────────────────────────────

def obtener_usuario_por_email(email):
    """Fetch user data by email for login."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, password_hash, nombre, rol, empresa_id, activo "
            "FROM usuarios WHERE email = %s",
            (email,),
        )
        return cur.fetchone()
    except Exception as exc:
        logger.error("Error fetching user: %s", exc)
        return None
    finally:
        cur.close()
        conn.close()


# ─── NOTA: init_iqi_db() ya NO se llama aquí automáticamente. ────────────────
# Se llama desde el lifespan de FastAPI en api_iqi.py.
