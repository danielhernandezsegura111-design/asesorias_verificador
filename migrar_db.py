# migrar_db.py
import sqlite3

db_path = "beneficiarios.db"  # Asegúrate de que el nombre coincida

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE beneficiarios ADD COLUMN fecha_registro TEXT")
    print("✅ Columna 'fecha_registro' agregada correctamente.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ️ La columna 'fecha_registro' ya existe. No se necesita migración.")
    else:
        print("❌ Error al modificar la tabla:", e)

conn.commit()
conn.close()
