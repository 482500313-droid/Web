# -*- coding: utf-8 -*-
"""
app.py — La Lonchería
Todo el backend en un solo archivo: modelos, rutas y configuración.

PARA INICIAR: python app.py
USUARIO ADMIN: admin@loncheria.com / admin1234
"""

import os
import random
from datetime import datetime

import stripe
from dotenv import load_dotenv
from flask import (Flask, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_dance.contrib.google import google, make_google_blueprint
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ── Carga variables del archivo .env ──────────────────────────
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Solo para desarrollo

# ── Configuración de la aplicación ────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"]                     = os.environ.get("SECRET_KEY", "loncheria_dev_2024")
app.config["SQLALCHEMY_DATABASE_URI"]        = "sqlite:///loncheria.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db            = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view             = "iniciar_sesion"
login_manager.login_message          = "Inicia sesión para continuar."
login_manager.login_message_category = "info"

CARPETA_IMAGENES       = os.path.join("static", "img", "productos")
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
NOMBRE                 = os.environ.get("NOMBRE_NEGOCIO", "La Lonchería")

# ── Google OAuth ──────────────────────────────────────────────
google_bp = make_google_blueprint(
    client_id     = os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET"),
    scope         = ["openid",
                     "https://www.googleapis.com/auth/userinfo.email",
                     "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to   = "callback_google",
)
app.register_blueprint(google_bp, url_prefix="/auth")


# =============================================================================
#  MODELOS (tablas de la base de datos)
# =============================================================================

class Categoria(db.Model):
    __tablename__ = "categorias"
    id        = db.Column(db.Integer, primary_key=True)
    nombre    = db.Column(db.String(80), unique=True, nullable=False)
    icono     = db.Column(db.String(10), default="")
    orden     = db.Column(db.Integer, default=0)
    productos = db.relationship("Producto", backref="categoria", lazy=True)


class Producto(db.Model):
    __tablename__ = "productos"
    id            = db.Column(db.Integer, primary_key=True)
    nombre        = db.Column(db.String(150), nullable=False)
    descripcion   = db.Column(db.Text, nullable=True)
    precio        = db.Column(db.Float, nullable=False)
    precio_oferta = db.Column(db.Float, nullable=True)
    imagen        = db.Column(db.String(300), nullable=True)
    stock         = db.Column(db.Integer, default=99)
    activo        = db.Column(db.Boolean, default=True)
    destacado     = db.Column(db.Boolean, default=False)
    tiempo_prep   = db.Column(db.Integer, default=15)
    categoria_id  = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=True)

    @property
    def precio_final(self):
        return self.precio_oferta if self.precio_oferta else self.precio

    @property
    def en_oferta(self):
        return self.precio_oferta is not None and self.precio_oferta < self.precio

    @property
    def disponible(self):
        return self.activo and self.stock > 0


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"
    id         = db.Column(db.Integer, primary_key=True)
    nombre     = db.Column(db.String(100), nullable=False)
    correo     = db.Column(db.String(150), unique=True, nullable=False)
    contrasena = db.Column(db.String(256), nullable=True)
    google_id  = db.Column(db.String(100), unique=True, nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    es_admin   = db.Column(db.Boolean, default=False)
    pedidos    = db.relationship("Pedido", backref="cliente", lazy=True)

    def establecer_contrasena(self, pw):
        self.contrasena = generate_password_hash(pw)

    def verificar_contrasena(self, pw):
        return self.contrasena and check_password_hash(self.contrasena, pw)


class Pedido(db.Model):
    __tablename__ = "pedidos"
    id              = db.Column(db.Integer, primary_key=True)
    numero_pedido   = db.Column(db.String(20), unique=True, nullable=False)
    usuario_id      = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    estado          = db.Column(db.String(30), default="pendiente")
    notas           = db.Column(db.Text, nullable=True)
    metodo_pago     = db.Column(db.String(20), default="efectivo")
    subtotal        = db.Column(db.Float, default=0.0)
    total           = db.Column(db.Float, default=0.0)
    stripe_session  = db.Column(db.String(200), nullable=True)
    pago_confirmado = db.Column(db.Boolean, default=False)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    detalles        = db.relationship("DetallePedido", backref="pedido", lazy=True,
                                      cascade="all, delete-orphan")

    ESTADOS = {
        "pendiente":      {"label": "Pendiente",  "color": "#F59E0B"},
        "confirmado":     {"label": "Confirmado", "color": "#3B82F6"},
        "en_preparacion": {"label": "Preparando", "color": "#8B5CF6"},
        "listo":          {"label": "Listo",      "color": "#10B981"},
        "entregado":      {"label": "Entregado",  "color": "#6B7280"},
        "cancelado":      {"label": "Cancelado",  "color": "#EF4444"},
    }

    @property
    def estado_info(self):
        return self.ESTADOS.get(self.estado, {"label": self.estado, "color": "#6B7280"})


class DetallePedido(db.Model):
    __tablename__ = "detalles_pedido"
    id          = db.Column(db.Integer, primary_key=True)
    pedido_id   = db.Column(db.Integer, db.ForeignKey("pedidos.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=True)
    cantidad    = db.Column(db.Integer, nullable=False, default=1)
    precio_unit = db.Column(db.Float, nullable=False)
    nombre_snap = db.Column(db.String(150))

    @property
    def subtotal(self):
        return self.precio_unit * self.cantidad


@login_manager.user_loader
def cargar_usuario(uid):
    return db.session.get(Usuario, int(uid))


#  FUNCIONES DE AYUDA

def contar_carrito():
    """Devuelve el total de artículos en el carrito."""
    return sum(a["cantidad"] for a in session.get("carrito", {}).values())


def generar_numero_pedido():
    """Genera un número único de pedido tipo PED-XXXX."""
    numero = random.randint(1000, 9999)
    while Pedido.query.filter_by(numero_pedido=f"PED-{numero}").first():
        numero = random.randint(1000, 9999)
    return f"PED-{numero}"


def extension_valida(nombre_archivo):
    """Verifica que el archivo sea una imagen permitida."""
    return "." in nombre_archivo and \
           nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


#  RUTAS — TIENDA

@app.route("/")
def inicio():
    cats      = Categoria.query.order_by(Categoria.orden).all()
    cat_id    = request.args.get("categoria", type=int)
    consulta  = Producto.query.filter_by(activo=True)
    if cat_id:
        consulta = consulta.filter_by(categoria_id=cat_id)
    productos = consulta.order_by(Producto.nombre).all()
    return render_template("inicio.html", categorias=cats, productos=productos,
                           cat_activa=cat_id, cnt=contar_carrito(), nombre=NOMBRE)


@app.route("/carrito")
def ver_carrito():
    carrito          = session.get("carrito", {})
    articulos, total = [], 0
    for pid, art in carrito.items():
        sub = art["precio"] * art["cantidad"]
        total += sub
        articulos.append({**art, "id": pid, "subtotal": sub})
    return render_template("carrito.html", articulos=articulos, total=total,
                           cnt=contar_carrito(), nombre=NOMBRE)


@app.route("/carrito/agregar/<int:pid>", methods=["POST"])
def agregar_al_carrito(pid):
    producto = db.get_or_404(Producto, pid)
    if not producto.disponible:
        return jsonify({"ok": False, "msg": "No disponible"}), 400
    carrito = session.get("carrito", {})
    clave   = str(pid)
    if clave in carrito:
        carrito[clave]["cantidad"] += 1
    else:
        carrito[clave] = {
            "nombre":   producto.nombre,
            "precio":   producto.precio_final,
            "imagen":   producto.imagen or "",
            "cantidad": 1,
        }
    session["carrito"] = carrito
    session.modified   = True
    total = sum(a["cantidad"] for a in carrito.values())
    return jsonify({"ok": True, "count": total, "msg": f"{producto.nombre} agregado"})


@app.route("/carrito/actualizar/<pid>", methods=["POST"])
def actualizar_cantidad(pid):
    cantidad = int(request.json.get("cantidad", 1))
    carrito  = session.get("carrito", {})
    if str(pid) in carrito:
        if cantidad <= 0:
            carrito.pop(str(pid))
        else:
            carrito[str(pid)]["cantidad"] = cantidad
    session["carrito"] = carrito
    session.modified   = True
    return jsonify({
        "ok":    True,
        "count": sum(a["cantidad"] for a in carrito.values()),
        "total": sum(a["precio"] * a["cantidad"] for a in carrito.values()),
    })


@app.route("/carrito/quitar/<pid>", methods=["POST"])
def quitar_del_carrito(pid):
    carrito = session.get("carrito", {})
    carrito.pop(str(pid), None)
    session["carrito"] = carrito
    session.modified   = True
    return jsonify({"ok": True, "count": sum(a["cantidad"] for a in carrito.values())})


#  RUTAS — AUTENTICACIÓN

@app.route("/login", methods=["GET", "POST"])
def iniciar_sesion():
    if current_user.is_authenticated:
        return redirect(url_for("inicio"))
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        pw     = request.form.get("contrasena", "")
        u      = Usuario.query.filter_by(correo=correo).first()
        if not u or not u.verificar_contrasena(pw):
            flash("Correo o contraseña incorrectos.", "error")
            return redirect(url_for("iniciar_sesion"))
        login_user(u, remember=True)
        flash(f"Hola, {u.nombre}!", "success")
        return redirect(url_for("inicio"))
    return render_template("login.html", nombre=NOMBRE, cnt=0)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("inicio"))
    if request.method == "POST":
        nombre    = request.form.get("nombre", "").strip()
        correo    = request.form.get("correo", "").strip().lower()
        pw        = request.form.get("contrasena", "")
        confirmar = request.form.get("confirmar", "")
        if not nombre or not correo or not pw:
            flash("Completa todos los campos.", "error")
            return redirect(url_for("registro"))
        if pw != confirmar:
            flash("Las contraseñas no coinciden.", "error")
            return redirect(url_for("registro"))
        if len(pw) < 6:
            flash("Mínimo 6 caracteres en la contraseña.", "error")
            return redirect(url_for("registro"))
        if Usuario.query.filter_by(correo=correo).first():
            flash("Ese correo ya está registrado.", "error")
            return redirect(url_for("iniciar_sesion"))
        u = Usuario(nombre=nombre, correo=correo)
        u.establecer_contrasena(pw)
        db.session.add(u)
        db.session.commit()
        login_user(u, remember=True)
        flash(f"Bienvenido/a, {nombre}!", "success")
        return redirect(url_for("inicio"))
    return render_template("registro.html", nombre=NOMBRE, cnt=0)


@app.route("/auth/google/authorized")
def callback_google():
    if not google.authorized:
        flash("No se pudo autenticar con Google.", "error")
        return redirect(url_for("iniciar_sesion"))
    try:
        info   = google.get("/oauth2/v2/userinfo").json()
        gid    = info.get("id")
        correo = info.get("email", "").lower()
        nombre = info.get("name", correo.split("@")[0])
        avatar = info.get("picture")
        u = (Usuario.query.filter_by(google_id=gid).first() or
             Usuario.query.filter_by(correo=correo).first())
        if u:
            u.google_id  = gid
            u.avatar_url = avatar
        else:
            u = Usuario(nombre=nombre, correo=correo, google_id=gid, avatar_url=avatar)
            db.session.add(u)
        db.session.commit()
        login_user(u, remember=True)
        flash(f"Bienvenido/a, {u.nombre}!", "success")
    except Exception:
        flash("Error al iniciar sesión con Google.", "error")
    return redirect(url_for("inicio"))


@app.route("/salir")
@login_required
def salir():
    logout_user()
    flash("Sesión cerrada. ¡Hasta pronto!", "info")
    return redirect(url_for("inicio"))


#  RUTAS — PEDIDOS

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def confirmar_pedido():
    carrito = session.get("carrito", {})
    if not carrito:
        flash("Tu carrito está vacío.", "info")
        return redirect(url_for("inicio"))

    articulos, total = [], 0
    for pid, art in carrito.items():
        sub = art["precio"] * art["cantidad"]
        total += sub
        articulos.append({**art, "id": pid, "subtotal": sub})

    if request.method == "POST":
        pago  = request.form.get("metodo_pago", "efectivo")
        notas = request.form.get("notas", "").strip()
        pedido = Pedido(
            numero_pedido = generar_numero_pedido(),
            usuario_id    = current_user.id,
            metodo_pago   = pago,
            notas         = notas,
            subtotal      = total,
            total         = total,
        )
        db.session.add(pedido)
        db.session.flush()
        for pid, art in carrito.items():
            db.session.add(DetallePedido(
                pedido_id   = pedido.id,
                producto_id = int(pid),
                cantidad    = art["cantidad"],
                precio_unit = art["precio"],
                nombre_snap = art["nombre"],
            ))
        db.session.commit()
        if pago == "stripe":
            return redirect(url_for("iniciar_pago", pedido_id=pedido.id))
        session["carrito"] = {}
        session.modified   = True
        flash(f"¡Pedido {pedido.numero_pedido} recibido!", "success")
        return redirect(url_for("detalle_pedido", numero=pedido.numero_pedido))

    return render_template("checkout.html", articulos=articulos, total=total,
                           cnt=contar_carrito(), nombre=NOMBRE)


@app.route("/mis-pedidos")
@login_required
def mis_pedidos():
    pedidos = Pedido.query.filter_by(usuario_id=current_user.id)\
              .order_by(Pedido.creado_en.desc()).all()
    return render_template("mis_pedidos.html", pedidos=pedidos,
                           cnt=contar_carrito(), nombre=NOMBRE)


@app.route("/pedido/<numero>")
@login_required
def detalle_pedido(numero):
    pedido = Pedido.query.filter_by(numero_pedido=numero).first_or_404()
    if pedido.usuario_id != current_user.id and not current_user.es_admin:
        return redirect(url_for("mis_pedidos"))
    return render_template("pedido_detalle.html", pedido=pedido,
                           cnt=contar_carrito(), nombre=NOMBRE)


@app.route("/pedido/estado/<numero>")
@login_required
def estado_pedido(numero):
    pedido = Pedido.query.filter_by(numero_pedido=numero).first_or_404()
    info   = pedido.estado_info
    return jsonify({"estado": pedido.estado, "label": info["label"]})


#  RUTAS — PAGO (Stripe)

@app.route("/pagar/<int:pedido_id>")
@login_required
def iniciar_pago(pedido_id):
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    pedido         = db.get_or_404(Pedido, pedido_id)

    # Modo demo si no hay clave real de Stripe
    if not stripe.api_key or "TU_" in stripe.api_key:
        pedido.pago_confirmado = True
        pedido.estado          = "confirmado"
        db.session.commit()
        session["carrito"] = {}
        session.modified   = True
        flash(f"Pedido {pedido.numero_pedido} confirmado (modo demo).", "success")
        return redirect(url_for("detalle_pedido", numero=pedido.numero_pedido))

    try:
        lineas = [
            {
                "price_data": {
                    "currency": "mxn",
                    "unit_amount": int(d.precio_unit * 100),
                    "product_data": {"name": d.nombre_snap},
                },
                "quantity": d.cantidad,
            }
            for d in pedido.detalles
        ]
        sesion_stripe = stripe.checkout.Session.create(
            payment_method_types = ["card"],
            line_items           = lineas,
            mode                 = "payment",
            success_url = url_for("pago_exitoso", pedido_id=pedido.id, _external=True),
            cancel_url  = url_for("confirmar_pedido", _external=True),
        )
        pedido.stripe_session = sesion_stripe.id
        db.session.commit()
        return redirect(sesion_stripe.url, code=303)
    except Exception as e:
        flash(f"Error de pago: {e}", "error")
        return redirect(url_for("confirmar_pedido"))


@app.route("/pago/exito/<int:pedido_id>")
@login_required
def pago_exitoso(pedido_id):
    pedido                 = db.get_or_404(Pedido, pedido_id)
    pedido.pago_confirmado = True
    pedido.estado          = "confirmado"
    db.session.commit()
    session["carrito"] = {}
    session.modified   = True
    return render_template("pago_exito.html", pedido=pedido, nombre=NOMBRE, cnt=0)


#  RUTAS — ADMINISTRADOR

def solo_admin():
    """Devuelve True si el usuario NO es admin (para bloquear acceso)."""
    return not (current_user.is_authenticated and current_user.es_admin)


@app.route("/admin")
@login_required
def panel_admin():
    if solo_admin():
        return redirect(url_for("inicio"))
    return render_template("admin_dashboard.html",
        total_pedidos   = Pedido.query.count(),
        pendientes      = Pedido.query.filter_by(estado="pendiente").count(),
        total_productos = Producto.query.filter_by(activo=True).count(),
        pedidos         = Pedido.query.order_by(Pedido.creado_en.desc()).limit(15).all(),
        nombre=NOMBRE, cnt=0)


@app.route("/admin/productos")
@login_required
def admin_productos():
    if solo_admin():
        return redirect(url_for("inicio"))
    return render_template("admin_productos.html",
        productos  = Producto.query.order_by(Producto.nombre).all(),
        categorias = Categoria.query.order_by(Categoria.orden).all(),
        nombre=NOMBRE, cnt=0)


@app.route("/admin/producto/nuevo",            methods=["GET", "POST"])
@app.route("/admin/producto/editar/<int:pid>", methods=["GET", "POST"])
@login_required
def formulario_producto(pid=None):
    if solo_admin():
        return redirect(url_for("inicio"))
    prod = db.get_or_404(Producto, pid) if pid else None
    cats = Categoria.query.order_by(Categoria.orden).all()

    if request.method == "POST":
        nombre    = request.form.get("nombre", "").strip()
        precio    = float(request.form.get("precio", 0))
        oferta    = request.form.get("precio_oferta", "").strip()
        cat_id    = request.form.get("categoria_id", type=int)
        desc      = request.form.get("descripcion", "").strip()
        stock     = request.form.get("stock", 99, type=int)
        t_prep    = request.form.get("tiempo_prep", 15, type=int)
        destacado = bool(request.form.get("destacado"))
        activo    = bool(request.form.get("activo"))

        imagen   = prod.imagen if prod else None
        archivo  = request.files.get("imagen")
        if archivo and archivo.filename and extension_valida(archivo.filename):
            os.makedirs(CARPETA_IMAGENES, exist_ok=True)
            nombre_archivo = secure_filename(archivo.filename)
            archivo.save(os.path.join(CARPETA_IMAGENES, nombre_archivo))
            imagen = f"img/productos/{nombre_archivo}"

        if prod:
            prod.nombre        = nombre
            prod.precio        = precio
            prod.descripcion   = desc
            prod.precio_oferta = float(oferta) if oferta else None
            prod.categoria_id  = cat_id
            prod.stock         = stock
            prod.tiempo_prep   = t_prep
            prod.destacado     = destacado
            prod.activo        = activo
            if imagen:
                prod.imagen = imagen
        else:
            prod = Producto(nombre=nombre, precio=precio, descripcion=desc,
                            precio_oferta=float(oferta) if oferta else None,
                            categoria_id=cat_id, stock=stock, tiempo_prep=t_prep,
                            destacado=destacado, imagen=imagen)
            db.session.add(prod)
        db.session.commit()
        flash(f"Producto '{nombre}' guardado.", "success")
        return redirect(url_for("admin_productos"))

    return render_template("admin_producto_form.html", prod=prod, cats=cats,
                           nombre=NOMBRE, cnt=0)


@app.route("/admin/producto/eliminar/<int:pid>", methods=["POST"])
@login_required
def desactivar_producto(pid):
    if solo_admin():
        return redirect(url_for("inicio"))
    prod        = db.get_or_404(Producto, pid)
    prod.activo = False
    db.session.commit()
    flash(f"'{prod.nombre}' desactivado.", "info")
    return redirect(url_for("admin_productos"))


@app.route("/admin/pedido/<int:pid>/estado", methods=["POST"])
@login_required
def actualizar_estado_pedido(pid):
    if solo_admin():
        return redirect(url_for("inicio"))
    pedido = db.get_or_404(Pedido, pid)
    nuevo  = request.form.get("estado")
    if nuevo in Pedido.ESTADOS:
        pedido.estado = nuevo
        db.session.commit()
        flash(f"{pedido.numero_pedido} → {Pedido.ESTADOS[nuevo]['label']}", "success")
    return redirect(url_for("panel_admin"))


#  INICIO — Datos por defecto y arranque del servidor

def sembrar_datos():
    """Crea categorías y el usuario admin si la base de datos está vacía."""
    if Categoria.query.count() == 0:
        db.session.add_all([
            Categoria(nombre="Tortas",      icono="", orden=1),
            Categoria(nombre="Tacos",       icono="", orden=2),
            Categoria(nombre="Quesadillas", icono="", orden=3),
            Categoria(nombre="Bebidas",     icono="", orden=4),
            Categoria(nombre="Extras",      icono="", orden=5),
        ])
    if not Usuario.query.filter_by(correo="admin@loncheria.com").first():
        admin = Usuario(nombre="Admin", correo="admin@loncheria.com", es_admin=True)
        admin.establecer_contrasena("admin1234")
        db.session.add(admin)
    db.session.commit()


# Crea las tablas y agrega datos iniciales al arrancar
with app.app_context():
    db.create_all()
    sembrar_datos()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)