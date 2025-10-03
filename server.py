from flask import Flask, request, jsonify, render_template, Response
import sqlite3, uuid, qrcode, os
from io import BytesIO
import base64
from datetime import datetime, timedelta
from admin_app import admin_bp

#---------------- CONFIGURACIÓN DE RUTA ABSOLUTA ----------------
BASEDIR = os.path.dirname(os.path.abspath(file_))
TEMPLATESDIR = os.path.join(BASEDIR, "templates")

app = Flask(name, templatefolder=TEMPLATESDIR)

#---------------- CREACIÓN DE TABLAS ----------------
def ensure_schema():
    conn = sqlite3.connect("beneficiarios.db")
    cursor = conn.cursor()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    conn.close()

#Llamar al inicio
ensure_schema()

#---------------- CONEXIÓN A LA BASE ----------------
def get_conn():
    conn = sqlite3.connect("beneficiarios.db")
    conn.row_factory = sqlite3.Row
    return conn

#---------------- OBTENER TIEMPO DE EXPIRACIÓN ----------------
def obtenertiempoexpira():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return int(row["valor"])
    return 3600  # por defecto 1 hora

#---------------- FUNCIÓN DE LIMPIEZA ----------------
def limpiar_expirados():
    """Resetea a PENDIENTE todos los beneficiarios RECLAMADO cuyo tiempo ya expiró."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cursor.fetchall()
    cambios = 0
    for row in rows:
        if row["fechaexpira"] and datetime.fromisoformat(row["fechaexpira"]) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios
                SET status='PENDIENTE', fechareclamo=NULL, fechaexpira=NULL
                WHERE id=?
            """, (row["id"],))
            cambios += 1
    conn.commit()
    conn.close()
    return cambios

#---------------- AUTENTICACIÓN BÁSICA PARA PANEL ----------------
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
    def decorated(args, *kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(args, *kwargs)
    decorated.name = f.name
    return decorated

#---------------- PÁGINA PRINCIPAL ----------------
@app.route("/")
def index():
    return render_template("form.html")

#---------------- REGISTRO DE USUARIO ----------------
@app.route("/registrar", methods=["POST"])
def registrar():
    nombre = request.form["nombre"].strip().upper()
    curp = request.form["curp"].strip().upper()

    # Validaciones
    if len(curp) != 18:
        return "❌ La CURP debe tener exactamente 18 caracteres"

    conn = get_conn()
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
    BASEURL = os.getenv("BASEURL", "http://localhost:5000")
    urlqr = f"{BASEURL}/verificar/{codigo}"

    qrimg = qrcode.make(urlqr)
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

#---------------- VERIFICACIÓN POR URL (GET) ----------------
@app.route("/verificar/<codigo>", methods=["GET"])
def verificarcodigoqr(codigo):
    limpiar_expirados()
    conn = get_conn()
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
    fechaexpira = row["fechaexpira"]

    if status == "RECLAMADO":
        if fechaexpira and datetime.fromisoformat(fechaexpira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status=?, fechareclamo=NULL, fechaexpira=NULL 
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
        segundos = obtenertiempoexpira()
        expira = datetime.now() + timedelta(seconds=segundos)
        cursor.execute("""
            UPDATE beneficiarios 
            SET status=?, fechareclamo=?, fechaexpira=? 
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

#---------------- VERIFICACIÓN POR JSON (POST) ----------------
@app.route("/verificar", methods=["POST"])
def verificar_post():
    limpiar_expirados()
    data = request.json
    codigo = data.get("codigo")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cursor.fetchone()

    if not row:
        return jsonify({"status": "no existe"})

    id_ = row["id"]
    nombre = row["nombre"]
    status = row["status"]
    fechaexpira = row["fechaexpira"]

    if status == "RECLAMADO":
        if fechaexpira and datetime.fromisoformat(fechaexpira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status=?, fechareclamo=NULL, fechaexpira=NULL 
                WHERE id=?
            """, ("PENDIENTE", id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return jsonify({"status": "ya reclamado", "nombre": nombre})

    segundos = obtenertiempoexpira()
    expira = datetime.now() + timedelta(seconds=segundos)
    cursor.execute("""
        UPDATE beneficiarios 
        SET status=?, fechareclamo=?, fechaexpira=? 
        WHERE id=?
    """, ("RECLAMADO", datetime.now().isoformat(), expira.isoformat(), id_))
    conn.commit()
    conn.close()

    return jsonify({"status": "puede reclamar", "nombre": nombre, "expira": expira.isoformat()})
# ---------------- ENDPOINT PARA CONFIGURAR TIEMPO ----------------
@app.route("/configurar_tiempo", methods=["POST"])
def configurar_tiempo():
    data = request.get_json(silent=True) or {}
    segundos = data.get("segundos")
    horas = data.get("horas")

    # Normaliza a segundos
    if segundos is None and horas is None:
        return jsonify({"error": "Debes enviar 'segundos' o 'horas'"}), 400
    if segundos is None and horas is not None:
        try:
            segundos = int(horas) * 3600
        except (ValueError, TypeError):
            return jsonify({"error": "El valor de 'horas' no es válido"}), 400
    else:
        try:
            segundos = int(segundos)
        except (ValueError, TypeError):
            return jsonify({"error": "El valor de 'segundos' no es válido"}), 400

    # Guarda en tabla config
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO config (clave, valor) VALUES (?, ?)
        ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
    """, ("tiempo_expira", str(segundos)))
    conn.commit()
    conn.close()

    return jsonify({"mensaje": f"Tiempo de expiración actualizado a {segundos} segundos"}), 200

# ---------------- ENDPOINT DE LIMPIEZA GENERAL ----------------
@app.route("/limpiar", methods=["POST"])
def limpiar_endpoint():
    cambios = limpiar_expirados()
    return jsonify({"mensaje": f"Se limpiaron {cambios} registros expirados"}), 200

# ---------------- PANEL DE CONTROL (BLUEPRINT) ----------------
app.register_blueprint(admin_bp, url_prefix="/admin")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    # Asegura esquema al iniciar (por si el proceso se reinicia)
    ensure_schema()
    port = int(os.environ.get("PORT", 5000))  # Render asigna el puerto
    print(f"Usando templates desde: {TEMPLATES_DIR}")
    app.run(host="0.0.0.0", port=port, debug=True)
