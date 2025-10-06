from flask import Flask, request, jsonify, render_template, Response
import sqlite3, uuid, qrcode, os
from io import BytesIO
import base64
from datetime import datetime, timedelta
from admin_app import admin_bp

# ---------------- CONFIGURACIÓN DE RUTA ABSOLUTA ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(__name__, template_folder=TEMPLATES_DIR)

# ---------------- CREACIÓN DE TABLAS ----------------
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
    cursor.execute("""
        INSERT OR IGNORE INTO config (clave, valor) VALUES ('tiempo_expira', '3600')
    """)
    conn.commit()
    conn.close()

ensure_schema()

# ---------------- CONEXIÓN A LA BASE ----------------
def get_conn():
    conn = sqlite3.connect("beneficiarios.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- OBTENER TIEMPO DE EXPIRACIÓN ----------------
def obtener_tiempo_expira():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cursor.fetchone()
    conn.close()
    return int(row["valor"]) if row else 3600

# ---------------- FUNCIÓN DE LIMPIEZA ----------------
def limpiar_expirados():
    conn = get_conn()
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

    if len(curp) != 18:
        return "❌ La CURP debe tener exactamente 18 caracteres"

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM beneficiarios WHERE nombre=? OR curp=?", (nombre, curp))
    existe = cursor.fetchone()
    if existe:
        conn.close()
        return "❌ El nombre o la CURP ya están registrados"

    codigo = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO beneficiarios (nombre, curp, codigo_unico, status) 
        VALUES (?,?,?,?)
    """, (nombre, curp, codigo, "PENDIENTE"))
    conn.commit()
    conn.close()

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

# ---------------- VERIFICACIÓN POR URL ----------------
@app.route("/verificar/<codigo>", methods=["GET"])
def verificar_codigo(codigo):
    limpiar_expirados()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return """
        <html>
        <head>
        <style>
        body {
            background: linear-gradient(to right, #434343, #000000);
            font-family: 'Segoe UI', sans-serif;
            color: white;
            text-align: center;
            padding-top: 100px;
        }
        .card {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 0 20px rgba(255,255,255,0.2);
            display: inline-block;
        }
        h1 {
            font-size: 60px;
            margin-bottom: 20px;
        }
        </style>
        </head>
        <body>
        <div class="card">
            <h1>❌ CÓDIGO NO ENCONTRADO</h1>
        </div>
        </body>
        </html>
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
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=?
            """, (id_,))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return f"""
            <html>
            <head>
            <style>
            body {{
                background: linear-gradient(to right, #ff4e50, #f9d423);
                font-family: 'Segoe UI', sans-serif;
                color: white;
                text-align: center;
                padding-top: 100px;
            }}
            .card {{
                background: rgba(0,0,0,0.3);
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 0 20px rgba(0,0,0,0.5);
                display: inline-block;
            }}
            h1 {{
                font-size: 60px;
                margin-bottom: 20px;
            }}
            p {{
                font-size: 24px;
            }}
            </style>
            </head>
            <body>
            <div class="card">
                <h1>🛑 YA RECLAMADO</h1>
                <p>{nombre} ({curp})</p>
            </div>
            </body>
            </html>
            """

    if status == "PENDIENTE":
        segundos = obtener_tiempo_expira()
        expira = datetime.now() + timedelta(seconds=segundos)
        cursor.execute("""
            UPDATE beneficiarios 
            SET status='RECLAMADO', fecha_reclamo=?, fecha_expira=? 
            WHERE id=?
        """, (datetime.now().isoformat(), expira.isoformat(), id_))
        conn.commit()
        conn.close()
        return f"""
        <html>
        <head>
        <style>
        body {{
            background: linear-gradient(to right, #a8e063, #56ab2f);
            font-family: 'Segoe UI', sans-serif;
            color: white;
            text-align: center;
            padding-top: 100px;
        }}
        .card {{
            background: rgba(0,0,0,0.3);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 0 20px rgba(0,0,0,0.5);
            display: inline-block;
        }}
        h1 {{
            font-size: 60px;
            margin-bottom: 20px;
        }}
        p {{
            font-size: 24px;
        }}
        </style>
        </head>
        <body>
        <div class="card">
            <h1>✅ VALIDADO</h1>
            <p>{nombre} ({curp})</p>
            <p>Reclamo válido hasta <strong>{expira.strftime('%H:%M:%S')}</strong></p>
        </div>
        </body>
        </html>
        """
# ---------------- VERIFICACIÓN POR JSON ----------------
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
        conn.close()
        return jsonify({"status": "no existe"})

    id_ = row["id"]
    nombre = row["nombre"]
    status = row["status"]
    fecha_expira = row["fecha_expira"]

    if status == "RECLAMADO":
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=?
            """, ("PENDIENTE", id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return jsonify({"status": "ya reclamado", "nombre": nombre})

    segundos = obtener_tiempo_expira()
    expira = datetime.now() + timedelta(seconds=segundos)
    cursor.execute("""
        UPDATE beneficiarios 
        SET status='RECLAMADO', fecha_reclamo=?, fecha_expira=? 
        WHERE id=?
    """, (datetime.now().isoformat(), expira.isoformat(), id_))
    conn.commit()
    conn.close()

    return jsonify({"status": "puede reclamar", "nombre": nombre, "expira": expira.isoformat()})

# ---------------- LIMPIEZA MANUAL ----------------
@app.route("/limpiar", methods=["POST"])
def limpiar_endpoint():
    cambios = limpiar_expirados()
    return jsonify({"mensaje": f"Se limpiaron {cambios} registros expirados"}), 200

# ---------------- PANEL ADMIN ----------------
app.register_blueprint(admin_bp, url_prefix="/admin")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Usando templates desde: {TEMPLATES_DIR}")
    app.run(host="0.0.0.0", port=port, debug=True)



