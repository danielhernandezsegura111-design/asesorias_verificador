from flask import Flask, request, jsonify, render_template, Response
import psycopg2, psycopg2.extras, uuid, qrcode, os
from io import BytesIO
import base64
from datetime import datetime, timedelta
from admin_app import admin_bp

# ---------------- CONFIGURACIÓN DE RUTA ABSOLUTA ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(__name__, template_folder=TEMPLATES_DIR)

# ---------------- CONEXIÓN A SUPABASE ----------------
def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT", "5432"),
        sslmode="require"
    )

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# ---------------- OBTENER TIEMPO DE EXPIRACIÓN ----------------
def obtener_tiempo_expira():
    conn = get_conn()
    cursor = get_cursor(conn)
    cursor.execute("SELECT valor FROM config WHERE clave=%s", ('tiempo_expira',))
    row = cursor.fetchone()
    conn.close()
    return int(row["valor"]) if row else 3600

# ---------------- FUNCIÓN DE LIMPIEZA ----------------
def limpiar_expirados():
    conn = get_conn()
    cursor = get_cursor(conn)
    cursor.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status=%s", ('RECLAMADO',))
    rows = cursor.fetchall()
    cambios = 0
    for row in rows:
        if row["fecha_expira"] and datetime.fromisoformat(row["fecha_expira"]) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios
                SET status=%s, fecha_reclamo=NULL, fecha_expira=NULL
                WHERE id=%s
            """, ('PENDIENTE', row["id"]))
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
    cursor = get_cursor(conn)
    cursor.execute("SELECT 1 FROM beneficiarios WHERE nombre=%s OR curp=%s", (nombre, curp))
    existe = cursor.fetchone()
    if existe:
        conn.close()
        return "❌ El nombre o la CURP ya están registrados"

    codigo = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO beneficiarios (nombre, curp, codigo_unico, status) 
        VALUES (%s, %s, %s, %s)
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
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=%s", (codigo,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return render_template("codigo_no_encontrado.html"), 404

    id_ = row["id"]
    nombre = row["nombre"]
    curp = row["curp"]
    status = row["status"]
    fecha_expira = row["fecha_expira"]

    if status == "RECLAMADO":
        if fecha_expira and datetime.fromisoformat(fecha_expira) < datetime.now():
            cursor.execute("""
                UPDATE beneficiarios 
                SET status=%s, fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=%s
            """, ('PENDIENTE', id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return render_template("ya_reclamado.html", nombre=nombre, curp=curp)

    if status == "PENDIENTE":
        segundos = obtener_tiempo_expira()
        expira = datetime.now() + timedelta(seconds=segundos)
        cursor.execute("""
            UPDATE beneficiarios 
            SET status=%s, fecha_reclamo=%s, fecha_expira=%s 
            WHERE id=%s
        """, ('RECLAMADO', datetime.now().isoformat(), expira.isoformat(), id_))
        conn.commit()
        conn.close()
        return render_template("validado.html", nombre=nombre, curp=curp, expira=expira.strftime('%H:%M:%S'))

# ---------------- VERIFICACIÓN POR JSON ----------------
@app.route("/verificar", methods=["POST"])
def verificar_post():
    limpiar_expirados()
    data = request.json
    codigo = data.get("codigo")

    conn = get_conn()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM beneficiarios WHERE codigo_unico=%s", (codigo,))
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
                SET status=%s, fecha_reclamo=NULL, fecha_expira=NULL 
                WHERE id=%s
            """, ('PENDIENTE', id_))
            conn.commit()
            status = "PENDIENTE"
        else:
            conn.close()
            return jsonify({"status": "ya reclamado", "nombre": nombre})

    segundos = obtener_tiempo_expira()
    expira = datetime.now() + timedelta(seconds=segundos)
    cursor.execute("""
        UPDATE beneficiarios 
        SET status=%s, fecha_reclamo=%s, fecha_expira=%s 
        WHERE id=%s
    """, ('RECLAMADO', datetime.now().isoformat(), expira.isoformat(), id_))
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

@app.route("/diagnostico", methods=["GET"])
def diagnostico():
    try:
        conn = get_conn()
        cursor = get_cursor(conn)
        cursor.execute("SELECT COUNT(*) FROM beneficiarios")
        total = cursor.fetchone()[0]
        conn.close()

        return f"""
        <h1>✅ Conexión exitosa</h1>
        <p>Hora del servidor: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Registros en beneficiarios: {total}</p>
        """
    except Exception as e:
        return f"""
        <h1>❌ Error de conexión</h1>
        <p>{str(e)}</p>
        """

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Usando templates desde: {TEMPLATES_DIR}")
    app.run(host="0.0.0.0", port=port, debug=True)




