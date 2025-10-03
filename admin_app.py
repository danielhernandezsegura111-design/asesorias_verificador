from flask import Blueprint, request, jsonify, Response
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

DB_NAME = "beneficiarios.db"

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# ---------------- AUTENTICACIÓN ----------------
USERNAME = "admin"
PASSWORD = "1234"

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        "Acceso restringido. Ingresa usuario y contraseña.\n",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ---------------- BASE DE DATOS ----------------
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_config():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    conn.close()

def guardar_tiempo(segundos=None, horas=None):
    valor = str(segundos) if segundos else str(int(horas) * 3600)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO config (clave, valor) VALUES (?, ?)", ("tiempo_expira", valor))
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

def limpiar_expirados():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cursor.fetchall()
    cambios = 0
    for id_, fecha_expira in rows:
        try:
            if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
                cursor.execute("""
                    UPDATE beneficiarios
                    SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                    WHERE id=?
                """, (id_,))
                cambios += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return cambios

# ---------------- PANEL ----------------
@admin_bp.route("/")
@requires_auth
def admin_panel():
    ensure_config()
    limpiar_expirados()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, curp, status, codigo_unico FROM beneficiarios")
    rows = cursor.fetchall()
    conn.close()

    menu = """
    <h1>Panel de Control</h1>
    <h3>Accesos rápidos</h3>
    <ul>
        <li><a href="/">Registro</a></li>
        <li><a href="/verificar/TEST-CODIGO">Verificación por QR (ejemplo)</a></li>
        <li><a href="/verificar">API de Verificación (POST)</a></li>
        <li><a href="/admin/configurar_tiempo">Configurar Tiempo</a></li>
        <li><a href="/limpiar">Limpieza</a></li>
    </ul>
    """

    tabla = """
    <h3>Beneficiarios registrados</h3>
    <table border=1 cellpadding=5>
        <tr>
            <th>ID</th><th>Nombre</th><th>CURP</th><th>Status</th><th>Código Único</th>
        </tr>
    """
    for row in rows:
        color = "#d9fcd9" if row["status"] == "PENDIENTE" else "#ffd6d6"
        tabla += f"<tr style='background-color:{color};'>"
        tabla += f"<td>{row['id']}</td><td>{row['nombre']}</td><td>{row['curp']}</td>"
        tabla += f"<td>{row['status']}</td><td>{row['codigo_unico']}</td></tr>"
    tabla += "</table>"

    return menu + tabla

# ---------------- CONFIGURAR TIEMPO ----------------
@admin_bp.route("/configurar_tiempo", methods=["GET", "POST"])
@requires_auth
def configurar_tiempo():
    ensure_config()
    if request.method == "GET":
        return """
        <h2>Configurar tiempo de renovación</h2>
        <form method="post">
            <label>Segundos: <input type="number" name="segundos"></label><br><br>
            <label>Horas: <input type="number" name="horas"></label><br><br>
            <button type="submit">Aplicar</button>
        </form>
        <p>También puedes usar POST con JSON: {"segundos":10} o {"horas":1}</p>
        """

    data = request.get_json(silent=True) or request.form
    segundos = data.get("segundos")
    horas = data.get("horas")

    if segundos:
        guardar_tiempo(segundos=segundos)
        return jsonify({"ok": True, "mensaje": f"Tiempo configurado en {segundos} segundos"})
    elif horas:
        guardar_tiempo(horas=horas)
        return jsonify({"ok": True, "mensaje": f"Tiempo configurado en {horas} horas"})
    else:
        return jsonify({"ok": False, "error": "Debes enviar 'segundos' o 'horas'"}), 400
