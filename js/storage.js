/**
 * storage.js — capa de abstracción de persistencia.
 *
 * TODA la app habla solo con este módulo. Nunca accede a localStorage
 * directamente desde otro módulo. Toda la API es async para que reemplazar
 * el cuerpo de cada función por fetch() sea transparente para el resto del código.
 *
 * Migración a backend: reemplazar la implementación interna de cada método.
 * El contrato (nombres + firmas) no cambia.
 */

const KEYS = {
  CART:    sucursalId => `isumos_cart:${sucursalId}`,
  ORDERS:  sucursalId => `isumos_orders:${sucursalId}`,
  SESSION: 'isumos_session',
};

/* Avisa una sola vez si quedan datos de la key global legada */
let _legacyOrdersWarned = false;
function _checkLegacyOrders() {
  if (!_legacyOrdersWarned && localStorage.getItem('isumos_orders') !== null) {
    console.warn('[storage] Clave isumos_orders global detectada — legado, ignorada');
    _legacyOrdersWarned = true;
  }
}

const storage = {

  /* ── Carrito ──────────────────────────────────────────────── */

  async getCart(sucursalId) {
    const raw = localStorage.getItem(KEYS.CART(sucursalId));
    return raw ? JSON.parse(raw) : { items: [] };
  },

  async saveCart(cart, sucursalId) {
    localStorage.setItem(KEYS.CART(sucursalId), JSON.stringify(cart));
  },

  /* ── Historial de pedidos (por sucursal) ──────────────────── */

  async getOrders(sucursalId) {
    _checkLegacyOrders();
    const raw = localStorage.getItem(KEYS.ORDERS(sucursalId));
    return raw ? JSON.parse(raw) : [];
  },

  async saveOrder(order, sucursalId) {
    const orders = await storage.getOrders(sucursalId);
    orders.unshift(order);
    localStorage.setItem(KEYS.ORDERS(sucursalId), JSON.stringify(orders));
    return order;
  },

  /* TODO: usar solo en vista centralizada de etapa 2, no en UI de sucursal */
  async getAllOrders() {
    const allKeys = Object.keys(localStorage).filter(k => k.startsWith('isumos_orders:'));
    const all = [];
    for (const key of allKeys) {
      try {
        const parsed = JSON.parse(localStorage.getItem(key));
        if (Array.isArray(parsed)) all.push(...parsed);
      } catch { /* key corrupta, ignorar */ }
    }
    return all.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
  },

  /* ── Sesión ───────────────────────────────────────────────── */

  async getSession() {
    const raw = localStorage.getItem(KEYS.SESSION);
    return raw ? JSON.parse(raw) : null;
  },

  async saveSession(data) {
    localStorage.setItem(KEYS.SESSION, JSON.stringify(data));
  },

  async clearSession() {
    localStorage.removeItem(KEYS.SESSION);
  },
};

export default storage;
