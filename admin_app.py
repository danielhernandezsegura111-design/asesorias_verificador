# admin_app.py (versión web para Render)
from flask import Blueprint
import sqlite3
from datetime import datetime

DB_NAME = "beneficiarios.db"

# Definimos el Blueprint
admin_bp = Blueprint("admin", __name__, template_folder="templates")

def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def limpiar_expirados():
    """Resetea a PENDIENTE todos los beneficiarios RECLAMADO cuyo tiempo ya expiró."""
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

@admin_bp.route("/")
def admin_panel():
    """Panel de control web en /admin"""
    limpiar_expirados()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, curp, status, codigo_unico FROM beneficiarios")
    rows = cursor.fetchall()
    conn.close()

    # Construir tabla HTML
    tabla = """
    <h1>Panel de control</h1>
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

    return tabla
