from flask import Flask, request, jsonify
import sqlite3, uuid, qrcode, os
from io import BytesIO
from utils import limpiar_expirados
import base64
from datetime import datetime, timedelta
import threading, time
from admin_app import admin_bp   # Panel admin
from config import DB_NAME       # ✅ Ruta centralizada

# ---------------- CONFIGURACIÓN ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# ---------------- BASE DE DATOS ----------------
def ensure_schema():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS beneficiarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            curp TEXT UNIQUE NOT NULL,
            codigo_unico TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'PENDIENTE',
            fecha_registro TEXT,
            fecha_reclamo TEXT,
            fecha_expira TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    conn.close()

ensure_schema()

def db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_config_seconds():
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT valor FROM config WHERE clave='tiempo_expira'")
    row = cur.fetchone()
    conn.close()
    return int(row["valor"]) if row else 1800  # 30 min por defecto

# ---------------- TAREA EN SEGUNDO PLANO ----------------
def tarea_background():
    while True:
        try:
            limpiar_expirados()
        except Exception as e:
            print("Error en tarea_background:", e)
        time.sleep(60)  # cada 60 segundos

# ---------------- PÁGINA PRINCIPAL ----------------
@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <title>Registro de Beneficiario</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body {
          background: linear-gradient(135deg, #007bff, #6610f2);
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          font-family: 'Segoe UI', sans-serif;
          padding: 20px;
        }
        .card {
          background: rgba(255,255,255,0.95);
          border-radius: 20px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.3);
          padding: 40px;
          width: 100%;
          max-width: 500px;
          animation: fadeIn 0.6s ease-in;
        }
        h1 {
          font-weight: 800;
          color: #343a40;
          margin-bottom: 10px;
          text-align: center;
          letter-spacing: 0.4px;
        }
        p.desc {
          text-align: center;
          color: #6c757d;
          margin-bottom: 25px;
        }
        .btn-primary {
          background: linear-gradient(90deg, #007bff, #6610f2);
          border: none;
          font-weight: 700;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .btn-primary:hover {
          transform: translateY(-1px);
          box-shadow: 0 6px 18px rgba(0,123,255,0.3);
        }
        @keyframes fadeIn {
          from {opacity: 0; transform: translateY(-12px);}
          to {opacity: 1; transform: translateY(0);}
        }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>Registro de beneficiario</h1>
        <p class="desc">Ingresa tu nombre y CURP para generar tu código QR.</p>
        <form action="/registrar" method="post">
          <div class="mb-3">
            <label class="form-label">Nombre completo</label>
            <input type="text" class="form-control" name="nombre" required>
          </div>
          <div class="mb-3">
            <label class="form-label">CURP</label>
            <input type="text" class="form-control" name="curp" maxlength="18" required>
          </div>
          <button type="submit" class="btn btn-primary w-100">Registrar y generar QR</button>
        </form>
      </div>
    </body>
    </html>
    """

# ---------------- REGISTRO ----------------
@app.route("/registrar", methods=["POST"])
def registrar():
    nombre = request.form.get("nombre", "").strip().upper()
    curp = request.form.get("curp", "").strip().upper()

    if len(curp) != 18:
        return """
        <html><body style="font-family: Arial; padding: 30px;">
        <h2>❌ La CURP debe tener exactamente 18 caracteres</h2>
        <p><a href="/">Volver</a></p>
        </body></html>
        """

    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM beneficiarios WHERE curp=?", (curp,))
    existente = cur.fetchone()

    if existente:
        cur.execute("UPDATE beneficiarios SET fecha_registro=? WHERE id=?", (datetime.now().isoformat(), existente["id"]))
        conn.commit()
        codigo = existente["codigo_unico"]
    else:
        codigo = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO beneficiarios (nombre, curp, codigo_unico, status, fecha_registro)
            VALUES (?,?,?,?,?)
        """, (nombre, curp, codigo, "PENDIENTE", datetime.now().isoformat()))
        conn.commit()
    conn.close()

    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
    url_qr = f"{BASE_URL}/verificar/{codigo}"

    qr_img = qrcode.make(url_qr)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <title>Registro exitoso</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body {{
          background: linear-gradient(135deg, #20c997, #0dcaf0);
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          font-family: 'Segoe UI', sans-serif;
          padding: 20px;
        }}
        .card {{
          background: rgba(255,255,255,0.95);
          border-radius: 20px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.3);
          padding: 40px;
          width: 100%;
          max-width: 560px;
          animation: fadeIn 0.6s ease-in;
          text-align: center;
        }}
        h1 {{ font-weight: 800; color: #198754; margin-bottom: 10px; }}
        .qr {{
          margin: 20px 0;
          border: 8px solid #19875422;
          border-radius: 12px;
        }}
        .btn {{
          font-weight: 700;
        }}
        @keyframes fadeIn {{
          from {{opacity: 0; transform: translateY(-12px);}}
          to {{opacity: 1; transform: translateY(0);}}
        }}
      </style>
    </head>
    <body>
      <div class="card">
        <h1>Registro exitoso</h1>
        <p><strong>Nombre:</strong> {nombre}</p>
        <p><strong>CURP:</strong> {curp}</p>
        <p>Escanea este QR para validar:</p>
        <img class="qr" src="data:image/png;base64,{qr_base64}" alt="QR">
        <p><strong>URL:</strong> <a href="{url_qr}" target="_blank">{url_qr}</a></p>
        <a href="/" class="btn btn-success">Registrar otro</a>
      </div>
    </body>
    </html>
    """

# ---------------- VERIFICACIÓN ----------------
@app.route("/verificar/<codigo>")
def verificar_codigo(codigo):
    limpiar_expirados()
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return """
        <html><body style="background:black;color:white;display:flex;justify-content:center;align-items:center;height:100vh;">
        <h1 style="font-size:3em;">❌ CÓDIGO NO ENCONTRADO</h1>
        </body></html>
        """, 404

    nombre, curp, status = row["nombre"], row["curp"], row["status"]

    def pagina_resultado(gradiente, icono, titulo, extra=""):
        return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
          <meta charset="UTF-8">
          <title>Comprobación</title>
          <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&display=swap" rel="stylesheet">
          <style>
            body {{
              margin: 0;
              font-family: 'Montserrat', sans-serif;
              display: flex;
              justify-content: center;
              align-items: center;
              height: 100vh;
              color: white;
              text-align: center;
              background: {gradiente};
              animation: fadeIn 0.6s ease-in;
            }}
            .card {{
              background: rgba(0,0,0,0.45);
              padding: 50px;
              border-radius: 25px;
              box-shadow: 0 10px 30px rgba(0,0,0,0.6);
              animation: zoomIn 0.7s ease;
              max-width: 720px;
            }}
            h1 {{
              font-size: 3.2em;
              margin-bottom: 12px;
              letter-spacing: 0.6px;
            }}
            .icon {{
              font-size: 7rem;
              margin-bottom: 18px;
              animation: pulse 1.6s infinite;
            }}
            .info {{
              font-size: 1.25em;
              margin-top: 18px;
            }}
            @keyframes fadeIn {{ from {{opacity:0;}} to {{opacity:1;}} }}
            @keyframes zoomIn {{ from {{transform: scale(0.9);}} to {{transform: scale(1);}} }}
            @keyframes pulse {{
              0% {{ transform: scale(1); }}
              50% {{ transform: scale(1.05); }}
              100% {{ transform: scale(1); }}
            }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="icon">{icono}</div>
            <h1>{titulo}</h1>
            <div class="info">
              <p><strong>Nombre:</strong> {nombre}</p>
              <p><strong>CURP:</strong> {curp}</p>
              {extra}
            </div>
          </div>
        </body>
        </html>
        """

    if status == "PENDIENTE":
        expira = datetime.now() + timedelta(seconds=get_config_seconds())
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE beneficiarios
            SET status='RECLAMADO', fecha_reclamo=?, fecha_expira=?
            WHERE id=?
        """, (datetime.now().isoformat(), expira.isoformat(), row["id"]))
        conn.commit()
        conn.close()
        return pagina_resultado(
            "linear-gradient(135deg, #28a745, #0b5d1e)",  # verde
            "✅",
            "VALIDADO",
            f"<p><strong>Disponible hasta:</strong> {expira.strftime('%d/%m/%Y %H:%M:%S')}</p>"
        )

    if status == "RECLAMADO":
        return pagina_resultado(
            "linear-gradient(135deg, #dc3545, #6a1a21)",  # rojo
            "❌",
            "YA RECLAMÓ",
            f"<p><strong>Podrá volver a reclamar después de:</strong> {row['fecha_expira'] or '—'}</p>"
        )

# ---------------- VERIFICACIÓN JSON ----------------
@app.route("/verificar", methods=["POST"])
def verificar_post():
    limpiar_expirados()
    data = request.json or {}
    codigo = data.get("codigo")

    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM beneficiarios WHERE codigo_unico=?", (codigo,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "no existe"}), 404

    status = row["status"]
    if status == "PENDIENTE":
        expira = datetime.now() + timedelta(seconds=get_config_seconds())
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE beneficiarios
            SET status='RECLAMADO', fecha_reclamo=?, fecha_expira=?
            WHERE id=?
        """, (datetime.now().isoformat(), expira.isoformat(), row["id"]))
        conn.commit()
        conn.close()
        return jsonify({"status": "validado", "nombre": row["nombre"], "expira": expira.isoformat()})

    return jsonify({"status": "ya reclamado", "nombre": row["nombre"], "expira": row["fecha_expira"]})

# ---------------- PANEL ----------------
app.register_blueprint(admin_bp, url_prefix="/admin")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    threading.Thread(target=tarea_background, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=True)



