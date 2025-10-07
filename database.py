# database.py
import sqlite3
from config import DB_NAME  # ✅ Usamos ruta absoluta compartida

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabla de beneficiarios
    cursor.execute("""
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

    # Tabla de configuración
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    # Valor inicial de tiempo de expiración
    cursor.execute("""
    INSERT OR IGNORE INTO config (clave, valor) VALUES ('tiempo_expira', '3600')
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()





