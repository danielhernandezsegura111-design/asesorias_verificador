import sqlite3

def init_db():
    conn = sqlite3.connect("beneficiarios.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS beneficiarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        curp TEXT UNIQUE NOT NULL,
        codigo_unico TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'no reclamado',
        fecha_reclamo TEXT,
        fecha_expira TEXT
    )
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()

