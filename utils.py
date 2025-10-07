# utils.py
import sqlite3
from datetime import datetime
from config import DB_NAME



def db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def limpiar_expirados():
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, fecha_expira FROM beneficiarios WHERE status='RECLAMADO'")
    rows = cur.fetchall()
    for row in rows:
        if row["fecha_expira"] and datetime.fromisoformat(row["fecha_expira"]) <= datetime.now():
            cur.execute("""
                UPDATE beneficiarios
                SET status='PENDIENTE', fecha_reclamo=NULL, fecha_expira=NULL
                WHERE id=?
            """, (row["id"],))
    conn.commit()
    conn.close()