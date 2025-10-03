from flask import Flask, request, jsonify, render_template, Response
import sqlite3, uuid, qrcode, os
from io import BytesIO
import base64
from datetime import datetime, timedelta

# ---------------- CONFIGURACIÓN DE RUTA ABSOLUTA ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATES_DIR)

# ---------------- CONFIGURACIÓN DE TIEMPO DE RENOVACIÓN ----------------
# Valor por defecto: 10 segundos (para pruebas)
TIEMPO_RENOVACION = timedelta(seconds=10)

# ---------------- CONEXIÓN A LA BASE ----------------
def db_connection():
    conn = sqlite3.connect("beneficiarios.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- FUNCIÓN DE LIMPIEZA ----------------
def limpiar_expirados():
    """Resetea a PENDIENTE todos los beneficiarios RECLAMADO cuyo tiempo ya expiró."""
    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cursor.fetchall()
    cambios = 0
    for row in rows:
        if row["fecha_expira"] and datetime.fromisoformat(row["fecha_expira"]) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                WHERE id=?
            """, (row["id"],))
            cambios += 1
    conn.commit()
    conn.close()
    return cambios

# ---------------- AUTENTICACIÓN BÁSICA PARA PANEL ----------------
USERNAME = "cerati"
PASSWORD = "123"

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        "Acceso restringido. Ingresa usuario y contraseña.", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# ---------------- PÁGINA PRINCIPAL ----------------
@app.route("/")
def index():
    return render_template("form.html")

# ---------------- REGISTRO DE USUARIO ----------------
@app.route("/registrar", methods=["POST"])
def registrar():
    nombre = request.form["nombre"].strip().upper()
    curp = request.form["curp"].strip().upper()

    # Validaciones
    if len(curp) != 18:
        return "❌ La CURP debe tener exactamente 18 caracteres"

    conn = db_connection()
    cursor = conn.cursor()

    # Verificar duplicados
    cursor.execute("SELECT 1 FROM beneficiarios WHERE nombre=? OR curp=?", (nombre, curp))
    existe = cursor.fetchone()
    if existe:
        conn.close()
        return "❌ El nombre o la CURP ya están registrados"

    # Insertar si pasa validaciones
    codigo = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO beneficiarios (nombre, curp, codigo_unico, status) 
        VALUES (?,?,?,?)
    """, (nombre, curp, codigo, "PENDIENTE"))
    conn.commit()
    conn.close()

    # Generar QR con la URL completa de verificación
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
    url_qr = f"{BASE_URL}/verificar/{codigo}"

    qr_img = qrcode.make(url_qr)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return f"""
    <h1>Registro exitoso</h1>
    <p>Nombre: {nombre}</p>
    <p>CURP: {curp}</p>
    <p>Escanea este QR para verificar:</p>
    <img src="data:image/png;base64,{qr_base64}">
    """

# ---------------- VERIFICACIÓN POR URL (GET) ----------------
@app.route("/verificar/<codigo>", methods=["GET"])
def verificar_codigo(codigo):
    limpiar_expirados()
    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return """
        <html><body style="background-color: gray; color: white; text-align:center;">
        <h1 style="font-size:50px;">❌ CÓDIGO NO ENCONTRADO</h1>
        </body></html>
        """, 404

    id_ = row["id"]
    nombre = row["nombre"]
    curp = row["curp"]
    status = row["status"]
    fecha_expira = row["fecha_expira"]

    if status == "RECLAMADO":
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status=?, fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=?
            """, ("PENDIENTE", id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return f"""
            <html><body style="background-color: red; color: white; text-align:center;">
            <h1 style="font-size:50px;">🟥 {nombre} ({curp}) YA RECLAMÓ</h1>
            </body></html>
            """

    if status == "PENDIENTE":
        expira = datetime.now() + TIEMPO_RENOVACION
        cursor.execute("""
            UPDATE beneficiarios 
            SET status=?, fecha_reclamo=?, fecha_expira=? 
            WHERE id=?
        """, ("RECLAMADO", datetime.now().isoformat(), expira.isoformat(), id_))
        conn.commit()
        conn.close()
        return f"""
        <html><body style="background-color: green; color: white; text-align:center;">
        <h1 style="font-size:50px;">🟩 {nombre} ({curp}) VALIDADO</h1>
        <p>Marcado como RECLAMADO hasta {expira.strftime("%H:%M:%S")}</p>
        </body></html>
        """

# ---------------- VERIFICACIÓN POR JSON (POST) ----------------
@app.route("/verificar", methods=["POST"])
def verificar_post():
    limpiar_expirados()
    data = request.json
    codigo = data.get("codigo")

    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cursor.fetchone()

    if not row:
        return jsonify({"status": "no existe"})

    id_ = row["id"]
    nombre = row["nombre"]
    status = row["status"]
    fecha_expira = row["fecha_expira"]

    if status == "RECLAMADO":
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status=?, fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=?
            """, ("PENDIENTE", id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return jsonify({"status": "ya reclamado", "nombre": nombre})

    expira = datetime.now() + TIEMPO_RENOVACION
    cursor.execute("""
        UPDATE beneficiarios 
        SET status=?, fecha_reclamo=?, fecha_expira=? 
        WHERE id=?
    """, ("RECLAMADO", datetime.now().isoformat(), expira.isoformat(), id_))
    conn.commit()
    conn.close()

    return jsonify({"status": "puede reclamar", "nombre": nombre})

# ---------------- ENDPOINT PARA CONFIGURAR TIEMPO ----------------
@app.route("/configurar_tiempo", methods=["POST"])
def configurar_tiempo():
    global TIEMPO_RENOVACION
    data = request.json
    if "segundos" in data:
        TIEMPO_RENOVACION = timedelta(seconds=data["segundos"])
    elif "horas" in data:
        TIEMPO_RENOVACION = timedelta(hours=data["horas"])
    else:
        return jsonify({"error": "Parámetros inválidos"}), 400
    return jsonify({"mensaje": f"Tiempo de renovación actualizado a {TIEMPO_RENOVACION}"}), 200

# ---------------- ENDPOINT DE LIMPIEZA GENERAL ----------------
@app.route("/limpiar", methods=["POST"])
def limpiar_endpoint():
    cambios = limpiar_expirados()
    return jsonify({"mensaje": f"Se limpiaron {cambios} registros expirados"}), 200

# ---------------- PANEL DE CONTROL (PROTEGIDO) ----------------
@app.route("/admin")
@requires_auth
def admin_panel():
    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, curp, status FROM beneficiarios")
    rows = cursor.fetchall()
    conn.close()

    # Generar una tabla simple con los beneficiarios
    tabla = "<table border=1><tr><th>Nombre</th><th>CURP</th><th>Status</th></tr>"
    for row in rows:
        tabla += f"<tr><td>{row['nombre']}</td><td>{row['curp']}</td><td>{row['status']}</td></tr>"
    tabla += "</table>"

    return f"<h1>Panel de control</h1>{tabla}"

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render asigna el puerto
    print(f"Usando templates desde: {TEMPLATES_DIR}")
    app.run(host="0.0.0.0", port=port, debug=True)




