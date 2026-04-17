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
  CART:    'isumos_cart',
  ORDERS:  'isumos_orders',
  SESSION: 'isumos_session',
};

const storage = {

  /* ── Carrito ──────────────────────────────────────────────── */

  async getCart() {
    const raw = localStorage.getItem(KEYS.CART);
    return raw ? JSON.parse(raw) : { items: [] };
  },

  async saveCart(cart) {
    localStorage.setItem(KEYS.CART, JSON.stringify(cart));
  },

  /* ── Historial de pedidos ─────────────────────────────────── */

  async getOrders() {
    const raw = localStorage.getItem(KEYS.ORDERS);
    return raw ? JSON.parse(raw) : [];
  },

  async saveOrder(order) {
    const orders = await storage.getOrders();
    orders.unshift(order);
    localStorage.setItem(KEYS.ORDERS, JSON.stringify(orders));
    return order;
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
