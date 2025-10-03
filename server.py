from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
from admin_app import admin_bp   # Importamos el Blueprint del admin

app = Flask(__name__)
app.register_blueprint(admin_bp, url_prefix="/admin")

DB_NAME = "beneficiarios.db"

# ---------------- BASE DE DATOS ----------------
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    conn = get_conn()
    cursor = conn.cursor()
    # Tabla de beneficiarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS beneficiarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            curp TEXT UNIQUE NOT NULL,
            codigo_unico TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'PENDIENTE',
            fecha_reclamo TEXT,
            fecha_expira TEXT
        )
    """)
    # Tabla de configuración
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    conn.close()

def obtener_tiempo_expira():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return int(row["valor"])
    return 3600  # por defecto 1 hora

# ---------------- RUTAS ----------------
@app.route("/")
def home():
    return "<h1>Bienvenido al sistema de registro</h1><p>Usa /admin para el panel</p>"

@app.route("/verificar/<codigo>", methods=["GET"])
def verificar_qr(codigo):
    """Verificación desde QR (GET)"""
    return verificar_codigo_interno(codigo)

@app.route("/verificar", methods=["POST"])
def verificar_api():
    """Verificación desde API (POST)"""
    data = request.get_json()
    codigo = data.get("codigo", "").strip()
    return verificar_codigo_interno(codigo, api=True)

def verificar_codigo_interno(codigo, api=False):
    if not codigo:
        return jsonify({"error": "Código no proporcionado"}), 400

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, status, fecha_expira FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "no encontrado"}), 404

    id_, nombre, status, fecha_expira = row["id"], row["nombre"], row["status"], row["fecha_expira"]

    # Si ya está reclamado, verificar si expiró
    if status == "RECLAMADO":
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            # Expirado → resetear
            cursor.execute("""
                UPDATE beneficiarios
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                WHERE id=?
            """, (id_,))
            conn.commit()
            conn.close()
            return jsonify({"status": "expirado", "nombre": nombre})
        else:
            conn.close()
            return jsonify({"status": "ya reclamado", "nombre": nombre})

    # Si está pendiente → marcar como reclamado
    segundos = obtener_tiempo_expira()
    expira = datetime.now() + timedelta(seconds=segundos)
    fecha_reclamo = datetime.now().isoformat()
    fecha_expira = expira.isoformat()

    cursor.execute("""
        UPDATE beneficiarios
        SET status='RECLAMADO', fecha_reclamo=?, fecha_expira=?
        WHERE id=?
    """, (fecha_reclamo, fecha_expira, id_))
    conn.commit()
    conn.close()

    return jsonify({"status": "puede reclamar", "nombre": nombre, "expira": fecha_expira})

@app.route("/limpiar")
def limpiar():
    """Resetea manualmente los expirados"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cursor.fetchall()
    cambios = 0
    for id_, fecha_expira in rows:
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                WHERE id=?
            """, (id_,))
            cambios += 1
    conn.commit()
    conn.close()
    return f"Se limpiaron {cambios} registros expirados."

# ---------------- MAIN ----------------
if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=5000)
