import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:asesorias@llalchbyrmgeeossgtbu.supabase.co:5432/postgres?sslmode=require")
    cursor = conn.cursor()
    cursor.execute("SELECT NOW();")
    print("✅ Conexión exitosa:", cursor.fetchone()[0])
    conn.close()
except Exception as e:
    print("❌ Error de conexión:", e)
