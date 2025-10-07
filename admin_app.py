from flask import Blueprint, request, jsonify, Response, redirect, url_for
import sqlite3
from utils import limpiar_expirados
from datetime import datetime
from functools import wraps
from config import DB_NAME
from flask import send_file

admin_bp = Blueprint("admin", __name__)

# ---------------- AUTENTICACIÓN ----------------
USERNAME = "admin"
PASSWORD = "1234"

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response("Acceso restringido.\n", 401,
                    {"WWW-Authenticate": 'Basic realm="Login Required"'})

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

def obtener_tiempo_config_segundos():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cur.fetchone()
    conn.close()
    return int(row["valor"]) if row else 1800  # 30 min por defecto

# ---------------- PANEL ----------------
@admin_bp.route("/")
@requires_auth
def admin_panel():
    # 🔹 refrescamos estados antes de mostrar
    limpiar_expirados()

    conn = get_conn()
    cur = conn.cursor()
    segundos = obtener_tiempo_config_segundos()
    cur.execute("SELECT * FROM beneficiarios ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    # Formulario de configuración + botón de eliminación masiva
    config_form = f"""
    <h1>Panel de Administración</h1>
    <h2>Configurar tiempo de renovación</h2>
    <form method="post" action="/admin/configurar_tiempo">
        <label>Duración:</label>
        <select name="segundos">
            <option value="40" {'selected' if segundos==40 else ''}>40 segundos</option>
            <option value="600" {'selected' if segundos==600 else ''}>10 minutos</option>
            <option value="1800" {'selected' if segundos==1800 else ''}>30 minutos</option>
            <option value="3600" {'selected' if segundos==3600 else ''}>1 hora</option>
            <option value="7200" {'selected' if segundos==7200 else ''}>2 horas</option>
        </select>
        <button type="submit">Aplicar</button>
    </form>
    <p>Tiempo actual configurado: {segundos} segundos</p>
    <hr>

    <h2>Eliminar todos los beneficiarios</h2>
    <form method="post" action="/admin/eliminar_todos" onsubmit="return confirm('¿Estás seguro de que deseas eliminar TODOS los beneficiarios? Esta acción no se puede deshacer.');">
        <button type="submit" style="background-color:#ff4d4d; color:white; padding:8px 16px; border:none; border-radius:4px;">Eliminar todos</button>
    </form>
    <hr>
    <h2>Descargar base de datos actual</h2>
    <form method="get" action="/admin/descargar_db">
        <button type="submit" style="background-color:#4CAF50; color:white; padding:8px 16px; border:none; border-radius:4px;">Descargar .db</button>
    </form>
    <hr>
    """
    # Tabla de beneficiarios
    tabla = """
    <h3>Beneficiarios</h3>
    <table style="border-collapse:collapse; width:100%; font-family:Arial; font-size:14px;">
        <tr style="background:#f0f0f0; text-align:center;">
            <th>ID</th><th>Nombre</th><th>CURP</th><th>Status</th>
            <th>Fecha registro</th><th>Último reclamo</th><th>Disponible hasta</th><th>Eliminar</th>
        </tr>
    """
    for row in rows:
        status = row["status"]
        color = "#d9fcd9" if status == "PENDIENTE" else "#ffd6d6"
        fecha_registro = row["fecha_registro"] or "—"
        fecha_reclamo = row["fecha_reclamo"] or "—"
        fecha_expira = row["fecha_expira"]

        if status == "RECLAMADO" and fecha_expira:
            disponible = datetime.fromisoformat(fecha_expira).strftime("%d/%m/%Y %H:%M:%S")
        else:
            disponible = "—"

        tabla += f"<tr style='background-color:{color}; text-align:center;'>"
        tabla += f"<td>{row['id']}</td><td>{row['nombre']}</td><td>{row['curp']}</td><td>{status}</td>"
        tabla += f"<td>{fecha_registro}</td><td>{fecha_reclamo}</td><td>{disponible}</td>"
        tabla += f"<td><form method='post' action='/admin/eliminar/{row['id']}' onsubmit=\"return confirm('¿Eliminar este usuario?');\"><button type='submit'>Eliminar</button></form></td></tr>"
    tabla += "</table>"

    return config_form + tabla

# ---------------- CONFIGURAR TIEMPO ----------------
@admin_bp.route("/configurar_tiempo", methods=["POST"])
@requires_auth
def configurar_tiempo():
    data = request.get_json(silent=True) or request.form
    segundos = data.get("segundos")
    try:
        segundos = int(segundos)
    except:
        return jsonify({"ok": False, "error": "Valor inválido"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO config (clave, valor) VALUES (?, ?)
        ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
    """, ("tiempo_expira", str(segundos)))
    conn.commit()
    conn.close()

    # 🔹 Redirigimos al panel para ver el cambio reflejado
    return redirect(url_for("admin.admin_panel"))

# ---------------- ELIMINAR USUARIO ----------------
@admin_bp.route("/eliminar/<int:id>", methods=["POST"])
@requires_auth
def eliminar_usuario(id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM beneficiarios WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin.admin_panel"))
@admin_bp.route("/eliminar_todos", methods=["POST"])
@requires_auth
def eliminar_todos():
    conn = get_conn()
    cur = conn.cursor()

    # 🔴 Eliminar todos los beneficiarios
    cur.execute("DELETE FROM beneficiarios")

    # 🔄 Reiniciar contador de ID
    cur.execute("DELETE FROM sqlite_sequence WHERE name='beneficiarios'")

    conn.commit()
    conn.close()
    return redirect(url_for("admin.admin_panel"))
@admin_bp.route("/descargar_db", methods=["GET"])
@requires_auth
def descargar_db():
    return send_file(DB_NAME, as_attachment=True)







