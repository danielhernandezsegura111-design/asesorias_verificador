import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3, uuid, qrcode
from PIL import Image, ImageTk
import requests
from datetime import datetime

# Cambia esta IP por la de tu PC si usas celular en la misma red
SERVER_URL = "http://192.168.1.68:5000"
DB_NAME = "beneficiarios.db"
# admin_app.py
from flask import Blueprint, render_template
import sqlite3

admin_bp = Blueprint("admin", __name__, template_folder="templates")

def db_connection():
    conn = sqlite3.connect("beneficiarios.db")
    conn.row_factory = sqlite3.Row
    return conn

@admin_bp.route("/")
def admin_panel():
    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, curp, status FROM beneficiarios")
    rows = cursor.fetchall()
    conn.close()

    tabla = "<table border=1><tr><th>Nombre</th><th>CURP</th><th>Status</th></tr>"
    for row in rows:
        tabla += f"<tr><td>{row['nombre']}</td><td>{row['curp']}</td><td>{row['status']}</td></tr>"
    tabla += "</table>"

    return f"<h1>Panel de control</h1>{tabla}"
# ---------------- UTILIDADES DE BASE DE DATOS ----------------
def get_conn():
    return sqlite3.connect(DB_NAME)

def ensure_schema():
    """Asegura que la tabla tenga las columnas requeridas."""
    conn = get_conn()
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
    # Verificar columnas faltantes por si la tabla existía antes
    cursor.execute("PRAGMA table_info(beneficiarios)")
    cols = {row[1] for row in cursor.fetchall()}
    if "fecha_reclamo" not in cols:
        cursor.execute("ALTER TABLE beneficiarios ADD COLUMN fecha_reclamo TEXT")
    if "fecha_expira" not in cols:
        cursor.execute("ALTER TABLE beneficiarios ADD COLUMN fecha_expira TEXT")
    conn.commit()
    conn.close()

def limpiar_expirados():
    """Resetea a PENDIENTE todos los beneficiarios RECLAMADO cuyo fecha_expira ya pasó."""
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
            # Si hay un formato inesperado, lo ignoramos
            continue
    conn.commit()
    conn.close()
    return cambios

def obtener_datos():
    limpiar_expirados()  # limpiar antes de mostrar
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, curp, status, codigo_unico FROM beneficiarios")
    rows = cursor.fetchall()
    conn.close()
    return rows

def agregar_usuario(nombre, curp):
    codigo = str(uuid.uuid4())
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO beneficiarios (nombre, curp, codigo_unico, status) VALUES (?,?,?,?)",
            (nombre, curp, codigo, "PENDIENTE")
        )
        conn.commit()
        conn.close()
        return codigo
    except sqlite3.IntegrityError:
        return None

def eliminar_usuario(id_usuario):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM beneficiarios WHERE id=?", (id_usuario,))
    conn.commit()
    conn.close()

def eliminar_todos():
    confirmar = messagebox.askyesno("Confirmar", "⚠️ Esto borrará TODOS los registros.\n¿Seguro que deseas continuar?")
    if confirmar:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM beneficiarios")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='beneficiarios'")
        conn.commit()
        conn.close()
        refrescar_tabla()
        label_qr.config(image="")
        messagebox.showinfo("Éxito", "Todos los registros fueron eliminados y el ID reiniciado")

# ---------------- FUNCIONES DE INTERFAZ ----------------
def refrescar_tabla():
    cambios = limpiar_expirados()
    for row in tree.get_children():
        tree.delete(row)
    for r in obtener_datos():
        # r: (id, nombre, curp, status, codigo_unico)
        status_tag = "pendiente" if r[3] == "PENDIENTE" else "reclamado"
        tree.insert("", tk.END, values=r, tags=(status_tag,))
    if cambios:
        status_bar.set(f"Registros expirados reseteados: {cambios}")
    else:
        status_bar.set("Tabla actualizada")

def accion_agregar():
    nombre = entry_nombre.get().strip().upper()
    curp = entry_curp.get().strip().upper()

    if not nombre or not curp:
        messagebox.showwarning("Error", "Debes ingresar nombre y CURP")
        return
    if len(curp) != 18:
        messagebox.showwarning("Error", "La CURP debe tener exactamente 18 caracteres")
        return

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM beneficiarios WHERE nombre=? OR curp=?", (nombre, curp))
    existe = cursor.fetchone()
    conn.close()
    if existe:
        messagebox.showerror("Error", "El nombre o la CURP ya están registrados")
        return

    codigo = agregar_usuario(nombre, curp)
    if codigo:
        # Generar QR con la URL completa
        url_qr = f"{SERVER_URL}/verificar/{codigo}"
        img = qrcode.make(url_qr)
        img.save("qr_temp.png")
        qr_img = Image.open("qr_temp.png").resize((200, 200))
        qr_tk = ImageTk.PhotoImage(qr_img)
        label_qr.config(image=qr_tk)
        label_qr.image = qr_tk
        messagebox.showinfo("Éxito", f"Usuario {nombre} agregado con éxito")
        entry_nombre.delete(0, tk.END)
        entry_curp.delete(0, tk.END)
        refrescar_tabla()
    else:
        messagebox.showerror("Error", "No se pudo registrar el usuario")

def accion_eliminar():
    seleccionado = tree.selection()
    if not seleccionado:
        messagebox.showwarning("Error", "Debes seleccionar un usuario de la tabla")
        return
    item = tree.item(seleccionado)
    id_usuario = item["values"][0]
    confirmar = messagebox.askyesno("Confirmar", "¿Seguro que deseas eliminar este usuario?")
    if confirmar:
        eliminar_usuario(id_usuario)
        refrescar_tabla()
        label_qr.config(image="")
        messagebox.showinfo("Eliminado", "Usuario eliminado correctamente")

# ---------------- VERIFICACIÓN DE QR ----------------
def comenzar_verificacion():
    ventana = tk.Toplevel(root)
    ventana.title("Verificación de QR")
    ventana.geometry("420x200")

    tk.Label(ventana, text="Pega aquí el código escaneado:", font=("Arial", 12)).pack(pady=10)
    entry_codigo = tk.Entry(ventana, width=40)
    entry_codigo.pack(pady=5)

    def mostrar_resultado(color_bg, texto, extra=""):
        ventana.destroy()
        nueva = tk.Toplevel(root)
        nueva.title("Resultado de Verificación")
        nueva.geometry("500x300")
        tk.Label(
            nueva, text=texto + ("\n" + extra if extra else ""),
            font=("Arial", 20, "bold"),
            bg=color_bg, fg="white"
        ).pack(fill="both", expand=True)

    def validar():
        codigo = entry_codigo.get().strip()
        if not codigo:
            messagebox.showwarning("Error", "Debes ingresar un código")
            return
        try:
            # POST para obtener JSON y aplicar la lógica del servidor
            r = requests.post(f"{SERVER_URL}/verificar", json={"codigo": codigo}, timeout=6)
            if r.status_code == 200:
                data = r.json()
                estado = data.get("status")
                nombre = data.get("nombre", "")
                if estado == "puede reclamar":
                    mostrar_resultado("green", f"🟩 {nombre} VALIDADO", "Marcado como RECLAMADO")
                elif estado == "ya reclamado":
                    mostrar_resultado("red", f"🟥 {nombre} YA RECLAMÓ")
                else:
                    mostrar_resultado("gray", "❌ CÓDIGO NO ENCONTRADO")
                refrescar_tabla()
            else:
                mostrar_resultado("orange", "Error del servidor")
        except Exception:
            mostrar_resultado("orange", "Error de conexión")

    tk.Button(ventana, text="Validar", command=validar).pack(pady=15)

# ---------------- CONFIGURACIÓN DE TIEMPO ----------------
def aplicar_tiempo():
    seleccion = combo_tiempo.get()
    if seleccion == "10 segundos":
        payload = {"segundos": 10}
    else:
        horas = int(seleccion.split()[0])
        payload = {"horas": horas}
    try:
        r = requests.post(f"{SERVER_URL}/configurar_tiempo", json=payload, timeout=6)
        if r.status_code == 200:
            messagebox.showinfo("Configuración", f"Tiempo de renovación establecido en {seleccion}")
        else:
            messagebox.showerror("Error", "No se pudo aplicar la configuración en el servidor")
    except Exception:
        messagebox.showerror("Error", "No se pudo conectar con el servidor")

# ---------------- INTERFAZ PRINCIPAL ----------------
ensure_schema()

root = tk.Tk()
root.title("Administrador de Beneficiarios")
root.geometry("1000x720")

# ----- Status bar -----
status_bar = tk.StringVar(value="Listo")
status_label = tk.Label(root, textvariable=status_bar, anchor="w")
status_label.pack(fill="x")

# ----- Frame de búsqueda -----
frame_busqueda = tk.Frame(root)
frame_busqueda.pack(pady=5, fill="x")

tk.Label(frame_busqueda, text="Buscar por nombre:").pack(side=tk.LEFT, padx=5)
entry_buscar = tk.Entry(frame_busqueda)
entry_buscar.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

def buscar_nombre():
    nombre = entry_buscar.get().strip().upper()
    if not nombre:
        refrescar_tabla()
        return
    limpiar_expirados()
    for row in tree.get_children():
        tree.delete(row)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, curp, status, codigo_unico FROM beneficiarios WHERE nombre LIKE ?",
        (f"%{nombre}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    for r in rows:
        status_tag = "pendiente" if r[3] == "PENDIENTE" else "reclamado"
        tree.insert("", tk.END, values=r, tags=(status_tag,))
    status_bar.set(f"Búsqueda: {len(rows)} resultados")

btn_buscar = tk.Button(frame_busqueda, text="Buscar", command=buscar_nombre)
btn_buscar.pack(side=tk.LEFT, padx=5)

btn_mostrar_todos = tk.Button(frame_busqueda, text="Mostrar todos", command=refrescar_tabla)
btn_mostrar_todos.pack(side=tk.LEFT, padx=5)

btn_refrescar = tk.Button(frame_busqueda, text="Refrescar tabla", command=refrescar_tabla)
btn_refrescar.pack(side=tk.LEFT, padx=5)

# ----- Formulario -----
frame_form = tk.Frame(root)
frame_form.pack(pady=10, fill="x")

tk.Label(frame_form, text="Nombre:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
entry_nombre = tk.Entry(frame_form, width=30)
entry_nombre.grid(row=0, column=1, padx=5, pady=5, sticky="w")

tk.Label(frame_form, text="CURP:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
entry_curp = tk.Entry(frame_form, width=30)
entry_curp.grid(row=1, column=1, padx=5, pady=5, sticky="w")

btn_agregar = tk.Button(frame_form, text="Agregar Usuario", command=accion_agregar)
btn_agregar.grid(row=2, column=0, columnspan=2, pady=10, sticky="we")

btn_eliminar = tk.Button(frame_form, text="Eliminar Usuario Seleccionado", command=accion_eliminar)
btn_eliminar.grid(row=3, column=0, columnspan=2, pady=10, sticky="we")

btn_eliminar_todos = tk.Button(
    frame_form, text="Eliminar TODOS los datos",
    command=eliminar_todos, bg="red", fg="white"
)
btn_eliminar_todos.grid(row=4, column=0, columnspan=2, pady=10, sticky="we")

# ----- Configuración de tiempo de renovación -----
frame_config = tk.Frame(root)
frame_config.pack(pady=10, fill="x")

tk.Label(frame_config, text="Tiempo de renovación:").pack(side=tk.LEFT, padx=5)

combo_tiempo = ttk.Combobox(
    frame_config,
    values=["10 segundos", "1 hora", "2 horas", "4 horas", "6 horas", "12 horas"],
    state="readonly", width=15
)
combo_tiempo.current(0)  # por defecto 10 segundos
combo_tiempo.pack(side=tk.LEFT, padx=5)

btn_aplicar_tiempo = tk.Button(frame_config, text="Aplicar", command=aplicar_tiempo)
btn_aplicar_tiempo.pack(side=tk.LEFT, padx=5)

# ----- Panel de QR -----
label_qr = tk.Label(root)
label_qr.pack(pady=10)

# ----- Tabla -----
tree = ttk.Treeview(
    root,
    columns=("ID", "Nombre", "CURP", "Status", "Codigo_unico"),
    show="headings", height=14
)
tree.heading("ID", text="ID")
tree.heading("Nombre", text="Nombre")
tree.heading("CURP", text="CURP")
tree.heading("Status", text="Status")
tree.heading("Codigo_unico", text="Código Único")

tree.column("ID", width=60, anchor="center")
tree.column("Nombre", width=220)
tree.column("CURP", width=200)
tree.column("Status", width=120, anchor="center")
tree.column("Codigo_unico", width=320)

# Colorear filas según status
style = ttk.Style()
style.map('Treeview', foreground=[('disabled', 'gray')], background=[('disabled', '#eee')])
tree.tag_configure("pendiente", background="#d9fcd9")   # verde claro
tree.tag_configure("reclamado", background="#ffd6d6")   # rojo claro

tree.pack(pady=10, fill="both", expand=True)

# ----- Botón para verificación -----
btn_verificar = tk.Button(
    root,
    text="Comenzar Verificación QR",
    command=comenzar_verificacion,
    bg="blue", fg="white"
)
btn_verificar.pack(pady=10)

# Inicializar tabla
refrescar_tabla()

root.mainloop()
