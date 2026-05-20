"""
Backend Isumos — Flask + SQLite  (Etapa 4)
Dos módulos que conviven:
  - Interno:  sucursales / depósito  (rutas existentes, sin cambios)
  - Ventas:   clientes externos / equipo de ventas / presupuestos
"""

import csv
import io
import json
import os
import queue
import threading
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

import jwt
from flask import Flask, Response, g, jsonify, request, send_from_directory, stream_with_context
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR          = Path(__file__).parent.parent
_data_env         = os.environ.get('DATA_DIR')
_DATA_DIR         = Path(_data_env) if _data_env else Path(__file__).parent
DB_PATH           = _DATA_DIR / 'isumos.db'
UPLOADS_DIR       = _DATA_DIR / 'uploads'
PRODUCTOS_IMG_DIR = (_DATA_DIR / 'img' / 'productos') if _data_env else (BASE_DIR / 'assets' / 'img' / 'productos')
SECRET_KEY   = os.environ.get('ISUMOS_SECRET', 'dev-secret-change-in-prod')
TOKEN_TTL    = int(os.environ.get('ISUMOS_TOKEN_TTL', 86400))

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path='')

# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        import sqlite3
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()

def _needs_full_migration():
    """Detecta si la DB es anterior a Etapa 3 (sin password_hash)."""
    import sqlite3
    if not DB_PATH.exists():
        return False
    db = sqlite3.connect(DB_PATH)
    try:
        db.execute('SELECT password_hash, sucursal_id FROM usuarios LIMIT 1')
        db.execute("SELECT id FROM pedidos WHERE estado='pendiente_aprobacion' LIMIT 1")
        return False
    except Exception:
        return True
    finally:
        db.close()

def _apply_additive_migrations(db):
    """Migraciones seguras: solo agrega, nunca borra datos existentes."""

    # ── Migrar rol CHECK de usuarios: quitar encargado y empleado ──
    needs_role_cleanup = False
    try:
        db.execute('SAVEPOINT sp_roles_v5')
        db.execute("INSERT INTO usuarios(id,sucursal_id,sucursal,usuario,password_hash,rol) "
                   "VALUES ('_chk2','_c','_c','_chk2_usr','_c','encargado')")
        db.execute("DELETE FROM usuarios WHERE id='_chk2'")
        db.execute('RELEASE SAVEPOINT sp_roles_v5')
        needs_role_cleanup = True
    except Exception:
        db.execute('ROLLBACK TO SAVEPOINT sp_roles_v5')
        db.execute('RELEASE SAVEPOINT sp_roles_v5')

    if needs_role_cleanup:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios_v5 (
                id            TEXT PRIMARY KEY,
                sucursal_id   TEXT NOT NULL,
                sucursal      TEXT NOT NULL,
                usuario       TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol           TEXT NOT NULL
                              CHECK(rol IN ('deposito','cliente','ventas','gerente')),
                empresa_id    TEXT
            );
            INSERT OR IGNORE INTO usuarios_v5
                SELECT id, sucursal_id, sucursal, usuario, password_hash, rol, empresa_id
                FROM usuarios
                WHERE rol NOT IN ('encargado', 'empleado');
            DROP TABLE usuarios;
            ALTER TABLE usuarios_v5 RENAME TO usuarios;
        """)
    else:
        try:
            db.execute('ALTER TABLE usuarios ADD COLUMN empresa_id TEXT')
        except Exception:
            pass

    # ── Columnas nuevas en productos ────────────────────────────────
    for stmt in [
        "ALTER TABLE productos ADD COLUMN tiempo_entrega_stock TEXT DEFAULT '24-48 hs'",
        "ALTER TABLE productos ADD COLUMN tiempo_entrega_sin_stock TEXT DEFAULT 'A consultar'",
    ]:
        try:
            db.execute(stmt)
        except Exception:
            pass

    db.commit()

def init_db():
    import sqlite3
    if _needs_full_migration() and DB_PATH.exists():
        print('[DB] Migrando esquema — borrando DB antigua')
        DB_PATH.unlink()

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # ── Tablas del módulo interno (sin cambios respecto a Etapa 3) ──
    db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id            TEXT PRIMARY KEY,
            sucursal_id   TEXT NOT NULL,
            sucursal      TEXT NOT NULL,
            usuario       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol           TEXT NOT NULL
                          CHECK(rol IN ('deposito','cliente','ventas','gerente')),
            empresa_id    TEXT
        );

        CREATE TABLE IF NOT EXISTS productos (
            sku_interno              TEXT PRIMARY KEY,
            codigo_barras            TEXT,
            nombre                   TEXT NOT NULL,
            presentacion             TEXT,
            unidad_pedido            TEXT,
            multiplo_minimo          INTEGER DEFAULT 1,
            categoria                TEXT,
            descripcion              TEXT,
            disponibilidad           TEXT DEFAULT 'disponible',
            es_controlado            INTEGER DEFAULT 0,
            imagen                   TEXT,
            tiempo_entrega_stock     TEXT DEFAULT '24-48 hs',
            tiempo_entrega_sin_stock TEXT DEFAULT 'A consultar'
        );

        CREATE TABLE IF NOT EXISTS carritos (
            sucursal_id TEXT PRIMARY KEY,
            items       TEXT NOT NULL DEFAULT '[]',
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id              TEXT PRIMARY KEY,
            sucursal_id     TEXT NOT NULL,
            sucursal_nombre TEXT NOT NULL,
            usuario         TEXT NOT NULL,
            rol             TEXT NOT NULL,
            fecha           TEXT NOT NULL,
            estado          TEXT NOT NULL DEFAULT 'pendiente'
                            CHECK(estado IN (
                                'pendiente_aprobacion','pendiente',
                                'preparando','despachado','recibido','rechazado'
                            )),
            items           TEXT NOT NULL
        );

        -- ── Módulo ventas (nuevo Etapa 4) ─────────────────────────

        CREATE TABLE IF NOT EXISTS empresas (
            id         TEXT PRIMARY KEY,
            nombre     TEXT NOT NULL,
            cuit       TEXT,
            email      TEXT,
            telefono   TEXT,
            direccion  TEXT,
            activa     INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS carritos_cliente (
            user_id    TEXT PRIMARY KEY,
            items      TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comentarios_presupuesto (
            id              TEXT PRIMARY KEY,
            presupuesto_id  TEXT NOT NULL,
            autor           TEXT NOT NULL,
            rol             TEXT NOT NULL,
            es_interno      INTEGER DEFAULT 0,
            texto           TEXT NOT NULL,
            fecha           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS adjuntos_presupuesto (
            id              TEXT PRIMARY KEY,
            presupuesto_id  TEXT NOT NULL,
            nombre          TEXT NOT NULL,
            tipo_mime       TEXT,
            tamano          INTEGER,
            saved_name      TEXT NOT NULL,
            subido_por      TEXT NOT NULL,
            rol_subido_por  TEXT NOT NULL,
            fecha           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS presupuestos (
            id               TEXT PRIMARY KEY,
            empresa_id       TEXT NOT NULL,
            empresa_nombre   TEXT NOT NULL,
            usuario_cliente  TEXT NOT NULL,
            usuario_ventas   TEXT,
            fecha_solicitud  TEXT NOT NULL,
            fecha_envio      TEXT,
            fecha_respuesta  TEXT,
            estado           TEXT NOT NULL DEFAULT 'solicitado'
                             CHECK(estado IN (
                                 'solicitado','en_revision','presupuestado',
                                 'aprobado','rechazado','en_preparacion',
                                 'despachado','entregado'
                             )),
            validez_dias     INTEGER DEFAULT 15,
            condiciones      TEXT,
            notas_cliente    TEXT,
            notas_ventas     TEXT,
            items            TEXT NOT NULL DEFAULT '[]'
        );
    """)

    _apply_additive_migrations(db)

    if db.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0] == 0:
        _seed_usuarios(db)
    else:
        _ensure_default_users(db)   # agrega usuarios nuevos sin tocar los existentes

    if db.execute('SELECT COUNT(*) FROM productos').fetchone()[0] == 0:
        _seed_productos(db)

    db.commit()
    db.close()

def _seed_usuarios(db):
    now = datetime.now(timezone.utc).isoformat()
    # Usuarios operativos
    for usuario, sucursal_id, sucursal, password, rol in [
        ('admin',    'ger001', 'Administración',   'admin123',    'gerente'),
        ('deposito', 'dep001', 'Depósito Central', 'deposito123', 'deposito'),
        ('ventas',   'ven001', 'Ventas',            'ventas123',   'ventas'),
    ]:
        db.execute(
            'INSERT OR IGNORE INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol) VALUES (?,?,?,?,?,?)',
            (str(uuid.uuid4()), sucursal_id, sucursal, usuario, generate_password_hash(password), rol)
        )
    # Sucursales como clientes
    for nombre, usuario, password in [
        ('Sucursal Centro', 'centro', 'centro123'),
        ('Sucursal Norte',  'norte',  'norte123'),
        ('Sucursal Sur',    'sur',    'sur123'),
    ]:
        eid = f'emp_{usuario}'
        db.execute(
            'INSERT OR IGNORE INTO empresas (id,nombre,created_at) VALUES (?,?,?)',
            (eid, nombre, now)
        )
        db.execute(
            'INSERT OR IGNORE INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol,empresa_id) VALUES (?,?,?,?,?,?,?)',
            (str(uuid.uuid4()), f'cli_{usuario}', nombre, usuario, generate_password_hash(password), 'cliente', eid)
        )

def _ensure_default_users(db):
    """Agrega usuarios de roles nuevos si no existen. No toca los existentes."""
    now = datetime.now(timezone.utc).isoformat()
    for usuario, sucursal_id, sucursal, password, rol in [
        ('admin',    'ger001', 'Administración',   'admin123',    'gerente'),
        ('deposito', 'dep001', 'Depósito Central', 'deposito123', 'deposito'),
        ('ventas',   'ven001', 'Ventas',            'ventas123',   'ventas'),
    ]:
        if not db.execute('SELECT id FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
            db.execute(
                'INSERT INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol) VALUES (?,?,?,?,?,?)',
                (str(uuid.uuid4()), sucursal_id, sucursal, usuario, generate_password_hash(password), rol)
            )
    for nombre, usuario, password in [
        ('Sucursal Centro', 'centro', 'centro123'),
        ('Sucursal Norte',  'norte',  'norte123'),
        ('Sucursal Sur',    'sur',    'sur123'),
    ]:
        eid = f'emp_{usuario}'
        if not db.execute('SELECT id FROM empresas WHERE id=?', (eid,)).fetchone():
            db.execute(
                'INSERT OR IGNORE INTO empresas (id,nombre,created_at) VALUES (?,?,?)',
                (eid, nombre, now)
            )
        if not db.execute('SELECT id FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
            db.execute(
                'INSERT INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol,empresa_id) VALUES (?,?,?,?,?,?,?)',
                (str(uuid.uuid4()), f'cli_{usuario}', nombre, usuario, generate_password_hash(password), 'cliente', eid)
            )
    db.commit()

def _seed_productos(db):
    path = BASE_DIR / 'productos.json'
    if not path.exists():
        return
    for p in json.loads(path.read_text()):
        db.execute("""
            INSERT OR IGNORE INTO productos
            (sku_interno,codigo_barras,nombre,presentacion,unidad_pedido,
             multiplo_minimo,categoria,descripcion,disponibilidad,es_controlado,imagen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p.get('sku_interno'), p.get('codigo_barras'), p.get('nombre'),
            p.get('presentacion'), p.get('unidad_pedido'),
            p.get('multiplo_minimo', 1), p.get('categoria'),
            p.get('descripcion'), p.get('disponibilidad', 'disponible'),
            1 if p.get('es_controlado') else 0, p.get('imagen')
        ))

# ── SSE pub/sub ───────────────────────────────────────────────────────────────

_subscribers: list[tuple] = []
_sub_lock = threading.Lock()

def _subscribe(predicate):
    q = queue.Queue(maxsize=100)
    with _sub_lock:
        _subscribers.append((predicate, q))
    return q

def _unsubscribe(q):
    with _sub_lock:
        _subscribers[:] = [(p, s) for p, s in _subscribers if s is not q]

def _publish(event: dict):
    with _sub_lock:
        subs = list(_subscribers)
    for predicate, q in subs:
        if predicate(event):
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

# ── Auth ──────────────────────────────────────────────────────────────────────

def _make_token(session: dict) -> str:
    payload = {**session, 'exp': datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL)}
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    except jwt.PyJWTError:
        return None

def require_auth(roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = (request.args.get('token') or
                     request.headers.get('Authorization', '').removeprefix('Bearer ').strip())
            if not token:
                return jsonify({'ok': False, 'motivo': 'no_token'}), 401
            payload = _decode_token(token)
            if not payload:
                return jsonify({'ok': False, 'motivo': 'token_invalido'}), 401
            rol = payload.get('rol')
            # gerente tiene acceso a todo excepto rutas exclusivas de cliente
            if roles and rol not in roles and not (rol == 'gerente' and 'cliente' not in roles):
                return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
            g.session = payload
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO INTERNO (sin cambios)
# ══════════════════════════════════════════════════════════════════════════════

# ── Rate limiter en memoria (login) ──────────────────────────────────────────
_login_attempts: dict = {}   # ip -> [timestamp, ...]
_RATE_LIMIT_MAX    = 5
_RATE_LIMIT_WINDOW = 900     # 15 minutos en segundos

def _check_rate_limit(ip: str) -> bool:
    """Devuelve True si la IP está bloqueada."""
    now   = datetime.now(timezone.utc).timestamp()
    times = [t for t in _login_attempts.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    _login_attempts[ip] = times
    return len(times) >= _RATE_LIMIT_MAX

def _record_failed_attempt(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    _login_attempts.setdefault(ip, []).append(now)

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)

@app.post('/api/auth/login')
def login():
    ip       = request.remote_addr or '0.0.0.0'
    if _check_rate_limit(ip):
        return jsonify({'ok': False, 'motivo': 'demasiados_intentos'}), 429

    data     = request.get_json(silent=True) or {}
    usuario  = data.get('usuario', '').strip()
    password = data.get('password', '').strip()
    if not usuario or not password:
        return jsonify({'ok': False, 'motivo': 'campos_requeridos'}), 400

    row = get_db().execute('SELECT * FROM usuarios WHERE usuario=?', (usuario,)).fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        _record_failed_attempt(ip)
        return jsonify({'ok': False, 'motivo': 'credenciales_invalidas'}), 401

    _clear_attempts(ip)

    rol = row['rol']
    # Para clientes: id = empresa_id (para que funcione como "sucursal_id" en el frontend)
    sucursal_id = row['empresa_id'] if rol == 'cliente' and row['empresa_id'] else row['sucursal_id']

    session = {
        'id':          sucursal_id,
        'sucursal_id': sucursal_id,
        'user_id':     row['id'],
        'sucursal':    row['sucursal'],
        'usuario':     row['usuario'],
        'rol':         rol,
    }
    if rol == 'cliente':
        session['empresa_id'] = row['empresa_id']

    return jsonify({'ok': True, 'session': session, 'token': _make_token(session)})

@app.post('/api/auth/logout')
def logout():
    return jsonify({'ok': True})

@app.post('/api/auth/refresh')
@require_auth()
def refresh_token():
    """Renueva el token JWT manteniendo los mismos datos de sesión."""
    session = g.session.copy()
    session.pop('exp', None)
    session.pop('iat', None)
    return jsonify({'ok': True, 'token': _make_token(session)})

# ── Productos ─────────────────────────────────────────────────────────────────

@app.get('/api/products')
@require_auth()
def get_products():
    rows = get_db().execute('SELECT * FROM productos').fetchall()
    return jsonify([dict(r) for r in rows])

@app.get('/api/products/demanda')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def get_demanda():
    """Conteo de pedidos por SKU en los últimos 30 días."""
    db   = get_db()
    dias = int(request.args.get('dias', 30))
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    pedidos = db.execute(
        "SELECT items FROM pedidos WHERE fecha >= ? AND estado != 'cancelado'", (desde,)
    ).fetchall()
    conteo: dict = {}
    for row in pedidos:
        try:
            items = json.loads(row['items'])
            for item in items:
                sku = item.get('sku') or item.get('sku_interno')
                if sku:
                    conteo[sku] = conteo.get(sku, 0) + item.get('qty', 1)
        except Exception:
            pass
    return jsonify(conteo)

@app.patch('/api/products/<sku>')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def update_product(sku):
    data    = request.get_json(silent=True) or {}
    allowed = {'disponibilidad', 'multiplo_minimo', 'nombre', 'descripcion',
               'tiempo_entrega_stock', 'tiempo_entrega_sin_stock',
               'categoria', 'presentacion'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'ok': False, 'motivo': 'sin_campos'}), 400
    db = get_db()
    if not db.execute('SELECT sku_interno FROM productos WHERE sku_interno=?', (sku,)).fetchone():
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE productos SET {set_clause} WHERE sku_interno=?', [*updates.values(), sku])
    db.commit()
    _publish({'tipo': 'catalogo_actualizado', 'sku': sku, **updates})
    return jsonify({'ok': True})

@app.get('/api/products/export')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def export_products():
    rows = get_db().execute('SELECT * FROM productos').fetchall()
    output = io.StringIO()
    fields = ['sku_interno','codigo_barras','nombre','presentacion','unidad_pedido',
              'multiplo_minimo','categoria','descripcion','disponibilidad',
              'es_controlado','tiempo_entrega_stock','tiempo_entrega_sin_stock']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="catalogo.csv"'}
    )

@app.post('/api/products/imagenes-bulk')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def upload_product_images_bulk():
    files = request.files.getlist('imagenes')
    if not files:
        return jsonify({'ok': False, 'motivo': 'sin_archivos'}), 400
    PRODUCTOS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    db      = get_db()
    ok      = []
    sin_match = []
    ALLOWED  = {'.jpg', '.jpeg', '.png', '.webp'}
    for f in files:
        ext  = Path(f.filename).suffix.lower()
        stem = Path(f.filename).stem
        if ext not in ALLOWED:
            sin_match.append(f.filename)
            continue
        row = db.execute('SELECT sku_interno FROM productos WHERE codigo_barras=?', (stem,)).fetchone()
        if not row:
            sin_match.append(f.filename)
            continue
        dest = PRODUCTOS_IMG_DIR / f'{stem}{ext}'
        f.save(dest)
        img_path = f'assets/img/productos/{stem}{ext}'
        db.execute('UPDATE productos SET imagen=? WHERE codigo_barras=?', (img_path, stem))
        ok.append(f.filename)
    db.commit()
    return jsonify({'ok': True, 'guardadas': len(ok), 'sin_match': sin_match})

@app.post('/api/products/<sku>/imagen')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def upload_product_image(sku):
    db      = get_db()
    product = db.execute('SELECT * FROM productos WHERE sku_interno=?', (sku,)).fetchone()
    if not product:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    f = request.files.get('imagen')
    if not f:
        return jsonify({'ok': False, 'motivo': 'sin_archivo'}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return jsonify({'ok': False, 'motivo': 'formato_invalido'}), 400
    PRODUCTOS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    barcode  = product['codigo_barras'] or sku
    filename = f'{barcode}{ext}'
    f.save(PRODUCTOS_IMG_DIR / filename)
    img_path = f'assets/img/productos/{filename}'
    db.execute('UPDATE productos SET imagen=? WHERE sku_interno=?', (img_path, sku))
    db.commit()
    return jsonify({'ok': True, 'imagen': img_path})

@app.post('/api/products/import')
@require_auth(roles=['deposito', 'ventas', 'gerente'])
def import_products():
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'motivo': 'sin_archivo'}), 400

    content = f.read().decode('utf-8-sig')   # utf-8-sig maneja BOM de Excel
    reader  = csv.DictReader(io.StringIO(content))
    db      = get_db()
    updated = created = errors = 0

    for row in reader:
        sku = (row.get('sku_interno') or '').strip()
        if not sku:
            errors += 1
            continue
        exists = db.execute('SELECT sku_interno FROM productos WHERE sku_interno=?', (sku,)).fetchone()
        try:
            if exists:
                allowed = ['nombre','presentacion','unidad_pedido','multiplo_minimo',
                           'categoria','descripcion','disponibilidad',
                           'tiempo_entrega_stock','tiempo_entrega_sin_stock','codigo_barras']
                updates = {k: row[k] for k in allowed if k in row and row[k] != ''}
                if updates:
                    set_clause = ', '.join(f'{k}=?' for k in updates)
                    db.execute(f'UPDATE productos SET {set_clause} WHERE sku_interno=?',
                               [*updates.values(), sku])
                updated += 1
            else:
                db.execute("""
                    INSERT INTO productos
                    (sku_interno,codigo_barras,nombre,presentacion,unidad_pedido,
                     multiplo_minimo,categoria,descripcion,disponibilidad,
                     es_controlado,tiempo_entrega_stock,tiempo_entrega_sin_stock)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    sku, row.get('codigo_barras',''),
                    row.get('nombre','Sin nombre'), row.get('presentacion',''),
                    row.get('unidad_pedido','unidad'),
                    int(row.get('multiplo_minimo') or 1),
                    row.get('categoria','General'), row.get('descripcion',''),
                    row.get('disponibilidad','disponible'),
                    1 if str(row.get('es_controlado','')).lower() in ('1','true','si','sí') else 0,
                    row.get('tiempo_entrega_stock','24-48 hs'),
                    row.get('tiempo_entrega_sin_stock','A consultar'),
                ))
                created += 1
        except Exception as e:
            errors += 1

    db.commit()
    return jsonify({'ok': True, 'creados': created, 'actualizados': updated, 'errores': errors})

# ── Carrito interno ───────────────────────────────────────────────────────────

@app.get('/api/cart/<sucursal_id>')
@require_auth()
def get_cart(sucursal_id):
    if g.session['id'] != sucursal_id and g.session['rol'] != 'deposito':
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    row = get_db().execute('SELECT items FROM carritos WHERE sucursal_id=?', (sucursal_id,)).fetchone()
    return jsonify({'items': json.loads(row['items']) if row else []})

@app.put('/api/cart/<sucursal_id>')
@require_auth()
def save_cart(sucursal_id):
    if g.session['id'] != sucursal_id:
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    data = request.get_json(silent=True) or {}
    now  = datetime.now(timezone.utc).isoformat()
    get_db().execute("""
        INSERT INTO carritos (sucursal_id, items, updated_at) VALUES (?,?,?)
        ON CONFLICT(sucursal_id) DO UPDATE SET items=excluded.items, updated_at=excluded.updated_at
    """, (sucursal_id, json.dumps(data.get('items', [])), now))
    get_db().commit()
    return jsonify({'ok': True})

# ── Pedidos internos ──────────────────────────────────────────────────────────

@app.get('/api/orders')
@require_auth()
def get_orders():
    sucursal_id = request.args.get('sucursal')
    session     = g.session
    if session['rol'] not in ('deposito',) and session['id'] != sucursal_id:
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    query  = 'SELECT * FROM pedidos WHERE sucursal_id=?'
    params = [sucursal_id]
    if estado := request.args.get('estado'):
        query += ' AND estado=?'; params.append(estado)
    if desde := request.args.get('desde'):
        query += ' AND fecha>=?'; params.append(desde)
    if hasta := request.args.get('hasta'):
        query += ' AND fecha<=?'; params.append(hasta + 'T23:59:59')
    query += ' ORDER BY fecha DESC'
    rows = get_db().execute(query, params).fetchall()
    return jsonify([_row_to_order(r) for r in rows])

@app.get('/api/orders/pending-approval')
@require_auth(roles=[])
def get_pending_approval():
    return jsonify({'ok': False, 'motivo': 'modulo_desactivado'}), 410

@app.post('/api/orders')
@require_auth()
def create_order():
    session = g.session
    data    = request.get_json(silent=True) or {}
    items   = data.get('items', [])
    if not items:
        return jsonify({'ok': False, 'motivo': 'empty'}), 400

    ts       = datetime.now(timezone.utc)
    order_id = f"{session['id']}-{int(ts.timestamp()*1000)}-{uuid.uuid4().hex[:4].upper()}"
    estado   = 'pendiente'

    order = {
        'id': order_id, 'sucursal_id': session['id'],
        'sucursal_nombre': session['sucursal'], 'usuario': session['usuario'],
        'rol': session['rol'], 'fecha': ts.isoformat(), 'estado': estado, 'items': items,
    }
    db = get_db()
    db.execute("""
        INSERT INTO pedidos (id,sucursal_id,sucursal_nombre,usuario,rol,fecha,estado,items)
        VALUES (?,?,?,?,?,?,?,?)
    """, (order['id'], order['sucursal_id'], order['sucursal_nombre'],
          order['usuario'], order['rol'], order['fecha'], order['estado'],
          json.dumps(order['items'])))
    db.execute("""
        INSERT INTO carritos (sucursal_id, items, updated_at) VALUES (?,?,?)
        ON CONFLICT(sucursal_id) DO UPDATE SET items='[]', updated_at=excluded.updated_at
    """, (session['id'], '[]', ts.isoformat()))
    db.commit()

    if estado == 'pendiente_aprobacion':
        _publish({'tipo': 'pedido_para_aprobar', 'sucursal_id': session['id'],
                  'order_id': order_id, 'usuario': session['usuario']})
    else:
        _publish({'tipo': 'nuevo_pedido', 'sucursal_id': session['id'],
                  'order_id': order_id, 'sucursal_nombre': session['sucursal']})
    return jsonify({'ok': True, 'order': order}), 201

@app.get('/api/orders/all')
@require_auth(roles=['deposito', 'gerente'])
def get_all_orders():
    conditions, params = [], []
    if estado := request.args.get('estado'):
        conditions.append('estado=?'); params.append(estado)
    if desde := request.args.get('desde'):
        conditions.append('fecha>=?'); params.append(desde)
    if hasta := request.args.get('hasta'):
        conditions.append('fecha<=?'); params.append(hasta + 'T23:59:59')
    query = 'SELECT * FROM pedidos'
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY fecha DESC'
    return jsonify([_row_to_order(r) for r in get_db().execute(query, params).fetchall()])

@app.patch('/api/orders/<order_id>')
@require_auth(roles=['deposito', 'gerente'])
def update_order_state(order_id):
    data    = request.get_json(silent=True) or {}
    estado  = data.get('estado')
    db      = get_db()
    row     = db.execute('SELECT * FROM pedidos WHERE id=?', (order_id,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    order = dict(row)
    if estado not in ('pendiente', 'preparando', 'despachado', 'recibido'):
        return jsonify({'ok': False, 'motivo': 'estado_invalido'}), 400
    db.execute('UPDATE pedidos SET estado=? WHERE id=?', (estado, order_id))
    db.commit()
    _publish({'tipo': 'estado_actualizado', 'order_id': order_id,
              'sucursal_id': order['sucursal_id'], 'estado': estado})
    if estado == 'pendiente':
        _publish({'tipo': 'nuevo_pedido', 'sucursal_id': order['sucursal_id'],
                  'order_id': order_id, 'sucursal_nombre': order['sucursal_nombre']})
    return jsonify({'ok': True, 'estado': estado})

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO VENTAS (nuevo Etapa 4)
# ══════════════════════════════════════════════════════════════════════════════

# ── Empresas ──────────────────────────────────────────────────────────────────

@app.get('/api/empresas')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def list_empresas():
    rows = get_db().execute('SELECT * FROM empresas ORDER BY nombre').fetchall()
    return jsonify([dict(r) for r in rows])

@app.post('/api/empresas')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def create_empresa():
    data = request.get_json(silent=True) or {}
    if not data.get('nombre'):
        return jsonify({'ok': False, 'motivo': 'nombre_requerido'}), 400
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    get_db().execute(
        'INSERT INTO empresas (id,nombre,cuit,email,telefono,direccion,activa,created_at) VALUES (?,?,?,?,?,?,1,?)',
        (eid, data['nombre'], data.get('cuit',''), data.get('email',''),
         data.get('telefono',''), data.get('direccion',''), now)
    )
    get_db().commit()
    return jsonify({'ok': True, 'id': eid}), 201

@app.patch('/api/empresas/<empresa_id>')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def update_empresa(empresa_id):
    data    = request.get_json(silent=True) or {}
    allowed = {'nombre', 'cuit', 'email', 'telefono', 'direccion', 'activa'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'ok': False, 'motivo': 'sin_campos'}), 400
    db = get_db()
    if not db.execute('SELECT id FROM empresas WHERE id=?', (empresa_id,)).fetchone():
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE empresas SET {set_clause} WHERE id=?', [*updates.values(), empresa_id])
    db.commit()
    return jsonify({'ok': True})

@app.post('/api/empresas/<empresa_id>/usuario')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def create_empresa_user(empresa_id):
    data    = request.get_json(silent=True) or {}
    usuario  = (data.get('usuario') or '').strip()
    password = (data.get('password') or '').strip()
    db = get_db()
    empresa = db.execute('SELECT * FROM empresas WHERE id=?', (empresa_id,)).fetchone()
    if not empresa:
        return jsonify({'ok': False, 'motivo': 'empresa_not_found'}), 404
    if not usuario or not password:
        return jsonify({'ok': False, 'motivo': 'campos_requeridos'}), 400
    if db.execute('SELECT id FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
        return jsonify({'ok': False, 'motivo': 'usuario_existe'}), 409
    db.execute(
        'INSERT INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol,empresa_id) VALUES (?,?,?,?,?,?,?)',
        (str(uuid.uuid4()), empresa_id, empresa['nombre'], usuario,
         generate_password_hash(password), 'cliente', empresa_id)
    )
    db.commit()
    return jsonify({'ok': True}), 201

# ── Carrito cliente ───────────────────────────────────────────────────────────

@app.get('/api/presupuestos/carrito')
@require_auth(roles=['cliente'])
def get_carrito_cliente():
    row = get_db().execute(
        'SELECT items FROM carritos_cliente WHERE user_id=?', (g.session['user_id'],)
    ).fetchone()
    return jsonify({'items': json.loads(row['items']) if row else []})

@app.put('/api/presupuestos/carrito')
@require_auth(roles=['cliente'])
def save_carrito_cliente():
    data = request.get_json(silent=True) or {}
    now  = datetime.now(timezone.utc).isoformat()
    get_db().execute("""
        INSERT INTO carritos_cliente (user_id, items, updated_at) VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET items=excluded.items, updated_at=excluded.updated_at
    """, (g.session['user_id'], json.dumps(data.get('items', [])), now))
    get_db().commit()
    return jsonify({'ok': True})

# ── Presupuestos ──────────────────────────────────────────────────────────────

@app.get('/api/presupuestos')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def list_presupuestos():
    session = g.session
    estado  = request.args.get('estado')
    db      = get_db()

    if session['rol'] == 'cliente':
        query  = 'SELECT * FROM presupuestos WHERE empresa_id=?'
        params = [session['empresa_id']]
    else:
        query, params = 'SELECT * FROM presupuestos', []
        if estado:
            query += ' WHERE estado=?'
            params.append(estado)

    query += ' ORDER BY fecha_solicitud DESC'
    rows   = db.execute(query, params).fetchall()
    return jsonify([_row_to_presupuesto(r) for r in rows])

@app.post('/api/presupuestos')
@require_auth(roles=['cliente'])
def create_presupuesto():
    session = g.session
    data    = request.get_json(silent=True) or {}
    items   = data.get('items', [])
    if not items:
        return jsonify({'ok': False, 'motivo': 'empty'}), 400

    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db  = get_db()
    db.execute("""
        INSERT INTO presupuestos
        (id,empresa_id,empresa_nombre,usuario_cliente,fecha_solicitud,estado,notas_cliente,items)
        VALUES (?,?,?,?,?,?,?,?)
    """, (pid, session['empresa_id'], session['sucursal'], session['usuario'],
          now, 'solicitado', data.get('notas_cliente',''), json.dumps(items)))

    # Limpiar carrito del cliente
    db.execute("""
        INSERT INTO carritos_cliente (user_id, items, updated_at) VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET items='[]', updated_at=excluded.updated_at
    """, (session['user_id'], '[]', now))
    db.commit()

    _publish({'tipo': 'nuevo_presupuesto', 'presupuesto_id': pid,
              'empresa_nombre': session['sucursal'], 'usuario': session['usuario']})
    return jsonify({'ok': True, 'id': pid}), 201

@app.get('/api/presupuestos/<pid>')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def get_presupuesto(pid):
    session = g.session
    row     = get_db().execute('SELECT * FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    p = _row_to_presupuesto(row)
    if session['rol'] == 'cliente' and p['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    return jsonify(p)

@app.patch('/api/presupuestos/<pid>')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def update_presupuesto(pid):
    """Ventas completa precios y datos del presupuesto."""
    data    = request.get_json(silent=True) or {}
    allowed = {'items', 'condiciones', 'notas_ventas', 'validez_dias', 'usuario_ventas'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'ok': False, 'motivo': 'sin_campos'}), 400

    db  = get_db()
    row = db.execute('SELECT id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404

    # Serializar items si viene como lista
    if 'items' in updates and isinstance(updates['items'], list):
        updates['items'] = json.dumps(updates['items'])

    # Marcar en_revision si todavía está en solicitado
    current = dict(db.execute('SELECT estado FROM presupuestos WHERE id=?', (pid,)).fetchone())
    if current['estado'] == 'solicitado':
        updates['estado'] = 'en_revision'

    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE presupuestos SET {set_clause} WHERE id=?', [*updates.values(), pid])
    db.commit()
    return jsonify({'ok': True})

@app.post('/api/presupuestos/<pid>/enviar')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def enviar_presupuesto(pid):
    """Ventas envía el presupuesto con precios al cliente."""
    db  = get_db()
    row = db.execute('SELECT * FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404

    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE presupuestos SET estado='presupuestado', fecha_envio=? WHERE id=?", (now, pid))
    db.commit()

    p = dict(row)
    _publish({'tipo': 'presupuesto_enviado', 'presupuesto_id': pid,
              'empresa_id': p['empresa_id']})
    return jsonify({'ok': True})

@app.post('/api/presupuestos/<pid>/aprobar')
@require_auth(roles=['cliente'])
def aprobar_presupuesto(pid):
    session = g.session
    db      = get_db()
    row     = db.execute('SELECT * FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    p = dict(row)
    if p['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    if p['estado'] != 'presupuestado':
        return jsonify({'ok': False, 'motivo': 'estado_invalido'}), 400

    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE presupuestos SET estado='aprobado', fecha_respuesta=? WHERE id=?", (now, pid))
    db.commit()
    _publish({'tipo': 'presupuesto_aprobado', 'presupuesto_id': pid,
              'empresa_nombre': p['empresa_nombre']})
    return jsonify({'ok': True})

@app.post('/api/presupuestos/<pid>/rechazar')
@require_auth(roles=['cliente'])
def rechazar_presupuesto(pid):
    session = g.session
    data    = request.get_json(silent=True) or {}
    db      = get_db()
    row     = db.execute('SELECT * FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    p = dict(row)
    if p['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403
    if p['estado'] != 'presupuestado':
        return jsonify({'ok': False, 'motivo': 'estado_invalido'}), 400

    now = datetime.now(timezone.utc).isoformat()
    motivo = data.get('motivo', '')
    db.execute("""
        UPDATE presupuestos SET estado='rechazado', fecha_respuesta=?,
        notas_cliente=COALESCE(notas_cliente||' | ','') || ? WHERE id=?
    """, (now, f'Rechazado: {motivo}' if motivo else 'Rechazado por el cliente', pid))
    db.commit()
    _publish({'tipo': 'presupuesto_rechazado', 'presupuesto_id': pid,
              'empresa_nombre': p['empresa_nombre']})
    return jsonify({'ok': True})

@app.patch('/api/presupuestos/<pid>/estado')
@require_auth(roles=['ventas', 'deposito', 'gerente'])
def update_presupuesto_estado(pid):
    data   = request.get_json(silent=True) or {}
    estado = data.get('estado')
    FLUJO  = ('en_preparacion', 'despachado', 'entregado')
    if estado not in FLUJO:
        return jsonify({'ok': False, 'motivo': 'estado_invalido'}), 400
    db  = get_db()
    row = db.execute('SELECT * FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    db.execute('UPDATE presupuestos SET estado=? WHERE id=?', (estado, pid))
    db.commit()
    p = dict(row)
    _publish({'tipo': 'presupuesto_actualizado', 'presupuesto_id': pid,
              'empresa_id': p['empresa_id'], 'estado': estado})
    return jsonify({'ok': True, 'estado': estado})

# ── SSE ───────────────────────────────────────────────────────────────────────

@app.get('/api/events')
@require_auth()
def sse_events():
    session = g.session
    sid     = session['id']
    rol     = session['rol']
    eid     = session.get('empresa_id')

    def predicate(event):
        tipo = event.get('tipo')
        if rol == 'deposito':
            return tipo in ('presupuesto_aprobado', 'presupuesto_actualizado',
                            'catalogo_actualizado', 'nuevo_presupuesto')
        if rol == 'gerente':
            return True
        if rol == 'ventas':
            return tipo in ('nuevo_presupuesto','presupuesto_aprobado','presupuesto_rechazado',
                            'nuevo_comentario') and event.get('para') in ('ventas', None)
        if rol == 'cliente':
            return ((tipo in ('presupuesto_enviado','presupuesto_actualizado','nuevo_adjunto') and
                     event.get('empresa_id') == eid) or
                    (tipo == 'nuevo_comentario' and event.get('empresa_id') == eid))
        return False

    q = _subscribe(predicate)

    @stream_with_context
    def generate():
        try:
            yield 'data: {"tipo":"conectado"}\n\n'
            while True:
                try:
                    event = q.get(timeout=25)
                    yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
                except queue.Empty:
                    yield ': keepalive\n\n'
        except GeneratorExit:
            pass
        finally:
            _unsubscribe(q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'},
    )

# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_order(row):
    d = dict(row)
    d['items'] = json.loads(d['items'])
    return d

def _row_to_presupuesto(row):
    d = dict(row)
    d['items'] = json.loads(d['items']) if d['items'] else []
    return d

# ── Servir frontend ───────────────────────────────────────────────────────────

@app.get('/assets/img/productos/<path:filename>')
def serve_producto_img(filename):
    return send_from_directory(str(PRODUCTOS_IMG_DIR), filename)

@app.get('/')
def index():
    return send_from_directory(str(BASE_DIR), 'login.html')

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    return send_from_directory(str(BASE_DIR), 'login.html')

# ── Entry point ───────────────────────────────────────────────────────────────

# ── Administración de usuarios ────────────────────────────────────────────────

@app.get('/api/usuarios')
@require_auth(roles=['deposito', 'gerente'])
def list_usuarios():
    rows = get_db().execute(
        'SELECT id, sucursal_id, sucursal, usuario, rol, empresa_id FROM usuarios ORDER BY rol, usuario'
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post('/api/usuarios')
@require_auth(roles=['deposito', 'gerente'])
def create_usuario():
    data     = request.get_json(silent=True) or {}
    usuario  = (data.get('usuario') or '').strip()
    password = (data.get('password') or '').strip()
    rol      = (data.get('rol') or '').strip()
    sucursal = (data.get('sucursal') or '').strip()
    ROLES_OPERATIVOS = ('deposito', 'ventas', 'gerente')

    if not usuario or not password or not rol or not sucursal:
        return jsonify({'ok': False, 'motivo': 'campos_requeridos'}), 400
    if rol not in ROLES_OPERATIVOS:
        return jsonify({'ok': False, 'motivo': 'rol_invalido'}), 400

    db = get_db()
    if db.execute('SELECT id FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
        return jsonify({'ok': False, 'motivo': 'usuario_existe'}), 409

    sucursal_id = f'{rol[:3]}_{usuario}'
    uid = str(uuid.uuid4())
    db.execute(
        'INSERT INTO usuarios (id,sucursal_id,sucursal,usuario,password_hash,rol) VALUES (?,?,?,?,?,?)',
        (uid, sucursal_id, sucursal, usuario, generate_password_hash(password), rol)
    )
    db.commit()
    return jsonify({'ok': True, 'id': uid}), 201

@app.patch('/api/usuarios/<uid>')
@require_auth(roles=['deposito', 'gerente'])
def update_usuario(uid):
    data    = request.get_json(silent=True) or {}
    db      = get_db()
    row     = db.execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404

    # No puede editarse a sí mismo para evitar quedarse sin acceso
    if uid == g.session['user_id']:
        return jsonify({'ok': False, 'motivo': 'no_puede_editarse_a_si_mismo'}), 400

    updates = {}
    if data.get('sucursal'):
        updates['sucursal'] = data['sucursal']
    if data.get('password'):
        updates['password_hash'] = generate_password_hash(data['password'])
    if data.get('rol') and data['rol'] in ('deposito', 'ventas', 'gerente'):
        updates['rol'] = data['rol']

    if not updates:
        return jsonify({'ok': False, 'motivo': 'sin_campos'}), 400

    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE usuarios SET {set_clause} WHERE id=?', [*updates.values(), uid])
    db.commit()
    return jsonify({'ok': True})

@app.delete('/api/usuarios/<uid>')
@require_auth(roles=['deposito', 'gerente'])
def delete_usuario(uid):
    db  = get_db()
    row = db.execute('SELECT rol FROM usuarios WHERE id=?', (uid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    if uid == g.session['user_id']:
        return jsonify({'ok': False, 'motivo': 'no_puede_eliminarse_a_si_mismo'}), 400
    if dict(row)['rol'] == 'cliente':
        return jsonify({'ok': False, 'motivo': 'usar_panel_empresas_para_clientes'}), 400
    db.execute('DELETE FROM usuarios WHERE id=?', (uid,))
    db.commit()
    return jsonify({'ok': True})

# ── Comentarios ───────────────────────────────────────────────────────────────

@app.get('/api/presupuestos/<pid>/comentarios')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def get_comentarios(pid):
    session = g.session
    p = get_db().execute('SELECT empresa_id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not p:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    if session['rol'] == 'cliente' and dict(p)['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403

    query = ('SELECT * FROM comentarios_presupuesto WHERE presupuesto_id=? AND es_interno=0 ORDER BY fecha'
             if session['rol'] == 'cliente'
             else 'SELECT * FROM comentarios_presupuesto WHERE presupuesto_id=? ORDER BY fecha')
    rows = get_db().execute(query, (pid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post('/api/presupuestos/<pid>/comentarios')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def add_comentario(pid):
    session = g.session
    data  = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto:
        return jsonify({'ok': False, 'motivo': 'texto_requerido'}), 400

    p = get_db().execute('SELECT empresa_id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not p:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    p = dict(p)
    if session['rol'] == 'cliente' and p['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403

    es_interno = 1 if (data.get('es_interno') and session['rol'] != 'cliente') else 0
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    get_db().execute(
        'INSERT INTO comentarios_presupuesto (id,presupuesto_id,autor,rol,es_interno,texto,fecha) VALUES (?,?,?,?,?,?,?)',
        (cid, pid, session['usuario'], session['rol'], es_interno, texto, now)
    )
    get_db().commit()

    if session['rol'] == 'cliente':
        _publish({'tipo': 'nuevo_comentario', 'presupuesto_id': pid, 'para': 'ventas',
                  'autor': session['usuario']})
    elif not es_interno:
        _publish({'tipo': 'nuevo_comentario', 'presupuesto_id': pid,
                  'empresa_id': p['empresa_id'], 'para': 'cliente', 'autor': session['usuario']})

    return jsonify({'ok': True, 'id': cid, 'fecha': now}), 201

# ── Adjuntos ──────────────────────────────────────────────────────────────────

@app.get('/api/presupuestos/<pid>/adjuntos')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def list_adjuntos(pid):
    session = g.session
    p = get_db().execute('SELECT empresa_id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not p:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    if session['rol'] == 'cliente' and dict(p)['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403

    rows = get_db().execute(
        'SELECT id,nombre,tipo_mime,tamano,subido_por,rol_subido_por,fecha FROM adjuntos_presupuesto WHERE presupuesto_id=? ORDER BY fecha',
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png'}
MAX_UPLOAD_BYTES   = 10 * 1024 * 1024   # 10 MB

# Firmas de bytes para validar el tipo real del archivo
FILE_SIGNATURES = {
    b'%PDF':           '.pdf',
    b'PK\x03\x04':    '.docx/.xlsx',  # ZIP-based Office formats
    b'\xd0\xcf\x11\xe0': '.doc/.xls', # Legacy Office formats
    b'\xff\xd8\xff':  '.jpg',
    b'\x89PNG':        '.png',
}

def _validate_upload(f) -> str | None:
    """Valida extensión y tipo real. Retorna motivo de error o None si es válido."""
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f'extension_no_permitida ({ext})'

    header = f.read(8)
    f.seek(0)

    valid_sig = any(header.startswith(sig) for sig in FILE_SIGNATURES)
    # Para .doc/.xls y .docx/.xlsx los primeros bytes son iguales — alcanza con verificar
    if not valid_sig:
        return 'tipo_archivo_invalido'

    # Verificar tamaño
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_UPLOAD_BYTES:
        return f'archivo_demasiado_grande (max 10 MB)'

    return None

@app.post('/api/presupuestos/<pid>/adjuntos')
@require_auth(roles=['ventas', 'deposito', 'cliente', 'gerente'])
def upload_adjunto(pid):
    session = g.session
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'motivo': 'sin_archivo'}), 400

    error = _validate_upload(f)
    if error:
        return jsonify({'ok': False, 'motivo': error}), 400

    p = get_db().execute('SELECT empresa_id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if not p:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404
    if session['rol'] == 'cliente' and dict(p)['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403

    upload_dir = UPLOADS_DIR / pid
    upload_dir.mkdir(parents=True, exist_ok=True)

    aid  = str(uuid.uuid4())
    ext  = Path(f.filename).suffix.lower()
    saved = f'{aid}{ext}'
    f.save(upload_dir / saved)
    size = (upload_dir / saved).stat().st_size
    now  = datetime.now(timezone.utc).isoformat()

    get_db().execute(
        'INSERT INTO adjuntos_presupuesto (id,presupuesto_id,nombre,tipo_mime,tamano,saved_name,subido_por,rol_subido_por,fecha) VALUES (?,?,?,?,?,?,?,?,?)',
        (aid, pid, f.filename, f.mimetype, size, saved,
         session['usuario'], session['rol'], now)
    )
    get_db().commit()

    _publish({'tipo': 'nuevo_adjunto', 'presupuesto_id': pid,
              'empresa_id': dict(p)['empresa_id'], 'nombre': f.filename})
    return jsonify({'ok': True, 'id': aid, 'nombre': f.filename, 'fecha': now, 'tamano': size}), 201

@app.get('/api/presupuestos/<pid>/adjuntos/<aid>')
@require_auth(roles=['cliente', 'ventas', 'deposito', 'gerente'])
def download_adjunto(pid, aid):
    session = g.session
    row = get_db().execute(
        'SELECT * FROM adjuntos_presupuesto WHERE id=? AND presupuesto_id=?', (aid, pid)
    ).fetchone()
    if not row:
        return jsonify({'ok': False, 'motivo': 'not_found'}), 404

    p = get_db().execute('SELECT empresa_id FROM presupuestos WHERE id=?', (pid,)).fetchone()
    if session['rol'] == 'cliente' and dict(p)['empresa_id'] != session.get('empresa_id'):
        return jsonify({'ok': False, 'motivo': 'sin_permiso'}), 403

    row = dict(row)
    return send_from_directory(str(UPLOADS_DIR / pid), row['saved_name'],
                               as_attachment=True, download_name=row['nombre'])

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    UPLOADS_DIR.mkdir(exist_ok=True)
    init_db()
    debug = os.environ.get('FLASK_ENV') != 'production'
    if not debug:
        print('Modo PRODUCCIÓN activo')
    else:
        print('⚠  Modo desarrollo — no exponer al exterior sin HTTPS y FLASK_ENV=production')
    print('DB lista en', DB_PATH)
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8000))
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    print(f'Acceso local:  http://localhost:{port}')
    print(f'Acceso en red: http://{ip}:{port}')
    app.run(host=host, debug=debug, port=port, threaded=True, use_reloader=False)
