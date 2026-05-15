/**
 * storage.js — capa de abstracción de persistencia. Etapa 3.
 */

const API = '/api';

function authHeaders() {
  const token = sessionStorage.getItem('isumos_token');
  return token
    ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw Object.assign(new Error(body.motivo ?? `HTTP ${res.status}`), { status: res.status, body });
  }
  return res.json();
}

const storage = {

  /* ── Carrito ──────────────────────────────────────────────── */

  async getCart(sucursalId) {
    return apiFetch(`/cart/${sucursalId}`);
  },

  async saveCart(cart, sucursalId) {
    await apiFetch(`/cart/${sucursalId}`, { method: 'PUT', body: JSON.stringify(cart) });
  },

  /* ── Pedidos ──────────────────────────────────────────────── */

  async getOrders(sucursalId) {
    return apiFetch(`/orders?sucursal=${sucursalId}`);
  },

  async saveOrder(order, _sucursalId) {
    const res = await apiFetch('/orders', { method: 'POST', body: JSON.stringify(order) });
    return res.order;
  },

  async getAllOrders(estado) {
    const qs = estado ? `?estado=${estado}` : '';
    return apiFetch(`/orders/all${qs}`);
  },

  /* ── Aprobación (encargado) ───────────────────────────────── */

  async getPendingApproval(sucursalId) {
    return apiFetch(`/orders/pending-approval?sucursal=${sucursalId}`);
  },

  async approveOrder(orderId) {
    return apiFetch(`/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ estado: 'pendiente' }),
    });
  },

  async rejectOrder(orderId) {
    return apiFetch(`/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ estado: 'rechazado' }),
    });
  },

  /* ── Estado pedido (depósito) ─────────────────────────────── */

  async updateOrderState(orderId, estado) {
    return apiFetch(`/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ estado }),
    });
  },

  /* ── Catálogo admin (depósito) ────────────────────────────── */

  async updateProduct(sku, data) {
    return apiFetch(`/products/${sku}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  /* ── Sesión (localStorage) ────────────────────────────────── */

  async getSession() {
    const raw = localStorage.getItem('isumos_session');
    return raw ? JSON.parse(raw) : null;
  },

  async saveSession(data) {
    localStorage.setItem('isumos_session', JSON.stringify(data));
  },

  async clearSession() {
    localStorage.removeItem('isumos_session');
    sessionStorage.removeItem('isumos_token');
  },
};

export default storage;
