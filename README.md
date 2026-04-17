# Isumos — Sistema de Pedidos Internos para Cadena de Farmacias

Web interna donde cada sucursal arma un carrito de reposición de productos. Diseñada como SPA vanilla (sin frameworks) para máxima portabilidad y facilidad de comprensión.

---

## Cómo correr localmente

Requiere un servidor HTTP para que los `import` de módulos ES6 y el `fetch` de JSON funcionen correctamente. No abrir `index.html` directamente desde el sistema de archivos.

```bash
# Python 3
cd "Proyecto Isumos"
python3 -m http.server 8000
# → http://localhost:8000/login.html
```

```bash
# Node.js (si tenés npx disponible)
npx serve .
```

**Credenciales de prueba:**

| Sucursal | Usuario | Password | Rol |
|---|---|---|---|
| Centro | `centro` | `centro123` | encargado |
| Norte | `norte` | `norte123` | encargado |
| Sur | `sur` | `sur456` | empleado |

---

## Estructura de carpetas

```
/
├── index.html              # Vista principal (catálogo, carrito, historial)
├── login.html              # Pantalla de login
├── productos.json          # Catálogo de productos (fuente de datos demo)
├── usuarios.json           # Credenciales hardcodeadas por sucursal
│
├── css/
│   ├── reset.css           # Normalize mínimo
│   ├── variables.css       # Design tokens: colores, tipografía, espaciados
│   ├── layout.css          # Estructura general, sidebar, bottom-sheet
│   ├── components.css      # Cards, chips, badges, modales, carrito
│   └── login.css           # Estilos específicos del login
│
├── js/
│   ├── app.js              # Orquestador: inicializa módulos, maneja navegación
│   ├── auth.js             # Login/logout, sesión activa, guard de ruta
│   ├── storage.js          # Capa de abstracción sobre localStorage (API async)
│   ├── catalog.js          # Carga productos, búsqueda, filtros por categoría
│   ├── cart.js             # Estado del carrito + reglas de negocio + persistencia
│   ├── cart-rules.js       # Reglas extraídas: múltiplo mínimo, validaciones
│   ├── barcode.js          # Comportamiento del scanner USB (autofocus, Enter)
│   └── views/
│       ├── catalog-view.js # Render de cards, filtros, modal de producto
│       ├── cart-view.js    # Render del carrito lateral / bottom-sheet
│       └── order-view.js   # Render de confirmación, historial, JSON del pedido
│
└── assets/
    └── img/
        └── productos/      # Imágenes de productos (JPG/PNG, 400x400px aprox.)
```

---

## Arquitectura de módulos

### `storage.js` — capa de abstracción (toda la persistencia pasa por acá)

API completamente `async`. Hoy escribe en `localStorage`; mañana reemplaza el cuerpo de cada función con `fetch` sin tocar el resto del código.

```js
await storage.getCart()
await storage.saveCart(cart)
await storage.getOrders()
await storage.saveOrder(order)
await storage.getSession()
await storage.saveSession(data)
await storage.clearSession()
```

### `cart.js` — reglas de negocio + persistencia automática

- `cart.add(sku, qty)` → redondea al múltiplo mínimo, rechaza `sin_stock`
- `cart.repeatLastOrder()` → recarga el último pedido validando disponibilidad
- Cada mutación (add/remove/updateQty/clear) persiste automáticamente vía `storage.saveCart()`

### `barcode.js` — scanner USB

- Autofocus al input de búsqueda al cargar y al cerrar modales/toasts
- Enter con match exacto de `codigo_barras` → agrega al carrito directo
- Enter con match parcial → filtra catálogo normalmente

---

## Etapa 2 — Pendiente (migración a backend)

Estos son los únicos archivos que necesitan cambios para conectar a una API real:

### `storage.js`
Reemplazar cada método `localStorage` por una llamada `fetch` al endpoint correspondiente. El resto del código no se toca.

```js
// Hoy:
async getCart() {
  return JSON.parse(localStorage.getItem('isumos_cart')) ?? { items: [] };
}

// Mañana:
async getCart() {
  const res = await fetch('/api/cart', { headers: authHeaders() });
  return res.json();
}
```

### `auth.js`
Reemplazar la validación contra `usuarios.json` por un POST a `/api/auth/login`. Gestionar JWT o cookie de sesión.

### Pendientes funcionales para Etapa 2
- [ ] Backend con base de datos (productos, pedidos, usuarios)
- [ ] Autenticación real (JWT / sesión server-side)
- [ ] Roles funcionales: empleado vs. encargado (aprobación de pedidos)
- [ ] Notificaciones al depósito central cuando llega un pedido
- [ ] Panel de administración para gestionar el catálogo
- [ ] Estados del pedido: pendiente → en preparación → despachado → recibido
- [ ] Integración con sistema de stock
