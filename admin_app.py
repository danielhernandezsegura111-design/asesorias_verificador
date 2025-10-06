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

def limpiar_expirados():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cursor.fetchall()
    cambios = 0
    for row in rows:
        try:
            if row["fecha_expira"] and datetime.fromisoformat(row["fecha_expira"]) < datetime.now():
                cursor.execute("""
                    UPDATE beneficiarios
                    SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                    WHERE id=?
                """, (row["id"],))
                cambios += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return cambios

def obtener_tiempo_expira():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cursor.fetchone()
    conn.close()
    return int(row["valor"]) if row else 3600

# ---------------- PANEL ----------------
@admin_bp.route("/")
@requires_auth
def admin_panel():
    limpiar_expirados()
    conn = get_conn()
    cursor = conn.cursor()

    tiempo_expira = obtener_tiempo_expira()

    cursor.execute("SELECT id, nombre, curp, status, codigo_unico, fecha_reclamo FROM beneficiarios")
    rows = cursor.fetchall()

    # Formulario desplegable
    config_form = f"""
    <h2>Configurar tiempo de renovación</h2>
    <form method="post" action="/admin/configurar_tiempo">
        <label>Selecciona duración:</label>
        <select name="segundos">
            <option value="40">40 segundos</option>
            <option value="1800">30 minutos</option>
            <option value="3600">1 hora</option>
            <option value="7200">2 horas</option>
            <option value="14400">4 horas</option>
            <option value="21600">6 horas</option>
            <option value="28800">8 horas</option>
            <option value="36000">10 horas</option>
            <option value="43200">12 horas</option>
        </select>
        <button type="submit">Aplicar</button>
    </form>
    <p>Tiempo actual configurado: {tiempo_expira} segundos</p>
    <hr>
    """

    # Tabla
    tabla = """
    <h3>Beneficiarios registrados</h3>
    <table border=1 cellpadding=5>
        <tr>
            <th>ID</th><th>Nombre</th><th>CURP</th><th>Status</th>
            <th>Código Único</th><th>Último Reclamo</th><th>Tiempo para volver a reclamar</th><th>Eliminar</th>
        </tr>
    """
    ahora = datetime.now()
    for row in rows:
        status = row["status"]
        color = "#d9fcd9" if status == "PENDIENTE" else "#ffd6d6"
        fecha_reclamo = row["fecha_reclamo"]

        if fecha_reclamo:
            dt_reclamo = datetime.fromisoformat(fecha_reclamo)
            restante = dt_reclamo + timedelta(seconds=tiempo_expira) - ahora
            if restante.total_seconds() <= 0:
                conn2 = get_conn()
                cursor2 = conn2.cursor()
                cursor2.execute("""
                    UPDATE beneficiarios
                    SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                    WHERE id=?
                """, (row["id"],))
                conn2.commit()
                conn2.close()
                status = "PENDIENTE"
                color = "#d9fcd9"
                tiempo_restante = "Disponible"
            else:
                tiempo_restante = f"{int(restante.total_seconds())} seg"
            hora_reclamo = dt_reclamo.strftime("%d/%m/%Y %H:%M:%S")
        else:
            tiempo_restante = "Disponible"
            hora_reclamo = "—"

        tabla += f"<tr style='background-color:{color};'>"
        tabla += f"<td>{row['id']}</td><td>{row['nombre']}</td><td>{row['curp']}</td>"
        tabla += f"<td>{status}</td><td>{row['codigo_unico']}</td>"
        tabla += f"<td>{hora_reclamo}</td><td>{tiempo_restante}</td>"
        tabla += f"<td><form method='post' action='/admin/eliminar/{row['id']}' onsubmit=\"return confirm('¿Eliminar este usuario?');\"><button type='submit'>Eliminar</button></form></td></tr>"
    tabla += "</table>"

    conn.close()
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
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO config (clave, valor) VALUES (?, ?)
        ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
    """, ("tiempo_expira", str(segundos)))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "mensaje": f"Tiempo configurado en {segundos} segundos"})

# ---------------- ELIMINAR USUARIO ----------------
@admin_bp.route("/eliminar/<int:id>", methods=["POST"])
@requires_auth
def eliminar_usuario(id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM beneficiarios WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "mensaje": f"Usuario {id} eliminado"})





