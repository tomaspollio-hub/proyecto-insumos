# Isumos — Sistema de Pedidos Internos

Web interna para cadenas de farmacias. Cada sucursal arma su carrito de reposición de productos, envía el pedido y consulta el historial. SPA vanilla sin frameworks — solo HTML, CSS y JS con módulos ES6.

---

## Cómo correr localmente

Requiere un servidor HTTP local: los módulos ES6 (`import/export`) y `fetch` no funcionan desde `file://`.

```bash
# Python 3
cd proyecto-isumos
python3 -m http.server 8000
# Abrir: http://localhost:8000/login.html
```

```bash
# Node.js
npx serve .
# Abrir la URL que muestra en consola + /login.html
```

---

## Credenciales de prueba

| Sucursal         | Usuario  | Contraseña  | Rol       |
|------------------|----------|-------------|-----------|
| Sucursal Centro  | `centro` | `centro123` | encargado |
| Sucursal Norte   | `norte`  | `norte123`  | encargado |
| Sucursal Sur     | `sur`    | `sur456`    | empleado  |

Los datos de sesión se guardan en `localStorage` bajo la key `isumos_session`. Cada sucursal tiene su carrito e historial aislados (`isumos_cart:{id}` e `isumos_orders:{id}`).

---

## Cómo testear

### Flujo básico
1. Ir a `http://localhost:8000/login.html`
2. Ingresar con cualquiera de las credenciales de arriba
3. Buscar un producto por nombre (ej: "ibuprofeno") o código de barras completo
4. Agregar al carrito desde el modal del producto o escaneando el código (Enter)
5. Abrir el carrito (sidebar derecha en desktop / tab inferior en mobile)
6. Hacer clic en **Revisar pedido** → verificar resumen agrupado por categoría
7. Hacer clic en **Enviar pedido** → ver pantalla de éxito con JSON del pedido
8. Hacer clic en **Historial** (ícono reloj en header) → ver pedido guardado
9. Expandir el pedido → hacer clic en **Repetir este pedido**

### Aislamiento por sucursal
1. Login como `centro`, agregar productos, enviar pedido
2. Logout → login como `norte`
3. Verificar que el carrito y el historial de `norte` están vacíos
4. El botón **Repetir último pedido** no aparece en `norte` (sin historial propio)

### Casos borde a probar
- **Múltiplo mínimo**: agregar Tramadol (múltiplo 2) con qty 1 → debe redondearse a 2
- **Sin stock**: Shampoo Anticaspa (sin_stock) → botón "Agregar" deshabilitado en modal
- **Producto controlado**: Tramadol → badge rojo "Controlado" en card y modal; aviso en confirmar pedido
- **Buscador + Enter**: escribir código de barras exacto (ej: `7790040031088`) y presionar Enter → agrega al carrito directo

---

## Estructura de archivos

```
/
├── index.html              # Vista principal (catálogo + carrito + historial)
├── login.html              # Pantalla de login
├── productos.json          # Catálogo de productos (fuente de datos demo)
├── usuarios.json           # Credenciales por sucursal (etapa 1)
│
├── css/
│   ├── variables.css       # Design tokens: colores, tipografía, espaciados
│   ├── reset.css           # Normalize mínimo
│   ├── layout.css          # Header, app-body, sidebar carrito, grid responsive
│   ├── components.css      # Cards, chips, badges, modales, carrito, historial
│   └── login.css           # Estilos exclusivos de login.html
│
├── js/
│   ├── auth.js             # Login / logout / requireAuth (guard de ruta)
│   ├── storage.js          # Capa de abstracción sobre localStorage (API async)
│   ├── catalog.js          # Carga productos, búsqueda, filtros por categoría
│   ├── cart.js             # Estado del carrito, reglas de negocio, persistencia
│   └── views/
│       ├── catalog-view.js # Render de cards, modal de producto, chips, toasts
│       ├── cart-view.js    # Render del panel carrito (sidebar / bottom-sheet)
│       └── order-view.js   # Render de confirmar pedido, éxito e historial
│
└── assets/
    └── img/
        ├── placeholder.svg         # Fallback para imágenes faltantes
        └── productos/              # Imágenes de productos (placeholder SVG por ahora)
```

---

## Arquitectura de módulos

### `storage.js` — toda la persistencia pasa por acá

API completamente `async`. Hoy escribe en `localStorage`; en Etapa 2 se reemplaza el cuerpo de cada función con un `fetch` sin tocar el resto del código.

```js
// Carrito aislado por sucursal
await storage.getCart(sucursalId)
await storage.saveCart(cart, sucursalId)

// Historial aislado por sucursal
await storage.getOrders(sucursalId)
await storage.saveOrder(order, sucursalId)

// Sesión (global, una por dispositivo)
await storage.getSession()
await storage.saveSession(data)
await storage.clearSession()

// Solo para vista centralizada de Etapa 2
await storage.getAllOrders()
```

Keys en `localStorage`:
- `isumos_session` — sesión activa
- `isumos_cart:{sucursalId}` — carrito por sucursal (ej: `isumos_cart:suc001`)
- `isumos_orders:{sucursalId}` — historial por sucursal (ej: `isumos_orders:suc002`)

### `cart.js` — reglas de negocio + persistencia automática

- `cart.add(sku, qty)` → rechaza `sin_stock`; redondea hacia arriba al múltiplo mínimo
- `cart.updateQty(sku, delta)` → delta ± respetando el múltiplo; elimina si qty ≤ 0
- `cart.submitOrder()` → genera ID `{sucursalId}-{timestamp}-{hash}`, guarda en historial, limpia carrito
- `cart.repeatOrder(orderId)` → recarga un pedido anterior validando disponibilidad actual; retorna `{ cargados, omitidos }`
- Cada mutación persiste automáticamente (nunca hay que llamar a `storage.saveCart` desde afuera)

### `catalog.js` — búsqueda y filtros

- `catalog.setCartAdd(fn)` — inyecta el callback del carrito (evita acoplamiento circular)
- `catalog.onSearch(query)` — filtra por nombre e includes/startsWith de código de barras simultáneamente
- `catalog.onEnter(query)` — si hay match exacto de código de barras, agrega al carrito directo (hook de scanner USB)
- Filtros de categoría: OR lógico, multi-seleccionables

---

## Etapas completadas

| Etapa | Qué se construyó |
|---|---|
| 1 | Sistema interno — login, catálogo, carrito, historial (localStorage) |
| 2 | Migración a backend Flask + SQLite, JWT, API REST, panel depósito |
| 3 | Roles funcionales (aprobación encargado), passwords hasheados, SSE tiempo real, admin catálogo |
| 4 | Módulo ventas corporativas: portal cliente, panel ventas, presupuestos, empresas, import/export CSV |
| 5 | IVA/descuento por ítem en presupuestos, comentarios cliente↔ventas (con notas internas), adjuntos de archivos |

---

## Pendiente — Etapa 6

### Integración con ERP ZETTI (zweb + Touch and Sale)

El módulo ventas está diseñado para conectarse a ZETTI cuando esté disponible la API.

| Dato | Dirección | Frecuencia |
|---|---|---|
| Lista de precios | ZETTI → plataforma | 1 vez/día o botón "actualizar" |
| Clientes / empresas | ZETTI → plataforma | 1 vez/día |
| Stock en tiempo real | ZETTI → plataforma | Cada 15 min o webhook |
| Presupuesto aprobado | Plataforma → ZETTI | Al instante |
| Remitos y facturas | ZETTI → plataforma | Al generarse en ZETTI |

**Requiere:** documentación de la API REST de zweb.

### Otras mejoras pendientes

- [ ] Notificación por email — requiere datos SMTP del servidor de correo (en gestión)
- [ ] Integración ZETTI — requiere documentación API de zweb (en gestión)
- [ ] Imágenes reales de productos en `assets/img/productos/`
- [ ] Historial de cambios de estado en cada presupuesto (auditoría)
- [ ] Múltiples usuarios por empresa cliente (hoy 1, el modelo de DB ya lo soporta)
