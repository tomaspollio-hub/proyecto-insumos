/**
 * cart.js — lógica del carrito. Persistencia automática en cada operación.
 * El consumidor nunca toca storage directamente.
 */

import storage from './storage.js';

const cart = {
  _items:    [],   // [{ sku, qty }]
  _products: {},   // { sku_interno: product }
  _session:  null,

  async init(session) {
    this._session = session;

    const token = sessionStorage.getItem('isumos_token');
    const res = await fetch('/api/products', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const list = await res.json();
    this._products = Object.fromEntries(list.map(p => [p.sku_interno, p]));

    const saved = await storage.getCart(session.id);
    this._items = saved.items ?? [];
  },

  /* ── Agregar ──────────────────────────────────────────────── */

  async add(sku, qty = 1) {
    const product = this._products[sku];
    if (!product)                              return { ok: false, motivo: 'not_found' };
    if (product.disponibilidad === 'sin_stock') return { ok: false, motivo: 'sin_stock' };

    const rounded = this._roundUp(qty, product.multiplo_minimo);

    const existing = this._items.find(i => i.sku === sku);
    if (existing) {
      existing.qty += rounded;
    } else {
      this._items.push({ sku, qty: rounded });
    }

    await this._persist();
    return { ok: true, qty_final: rounded, ajustado: rounded !== qty };
  },

  /* ── Eliminar ─────────────────────────────────────────────── */

  async remove(sku) {
    this._items = this._items.filter(i => i.sku !== sku);
    await this._persist();
  },

  /* ── Actualizar cantidad (delta +/-) ─────────────────────── */

  async updateQty(sku, delta) {
    const item = this._items.find(i => i.sku === sku);
    if (!item) return;

    const multiple = this._products[sku]?.multiplo_minimo ?? 1;
    const next = item.qty + delta;

    if (next <= 0) {
      return this.remove(sku);
    }

    item.qty = this._roundUp(next, multiple);
    await this._persist();
  },

  /* ── Vaciar ───────────────────────────────────────────────── */

  async clear() {
    this._items = [];
    await this._persist();
  },

  /* ── Consultas ────────────────────────────────────────────── */

  getItems() {
    return this._items
      .map(item => ({ ...item, product: this._products[item.sku] ?? null }))
      .filter(i => i.product !== null);
  },

  getSummary() {
    const items = this.getItems();
    return {
      total_items:  items.length,
      total_bultos: items.reduce((sum, i) => sum + i.qty, 0),
    };
  },

  /* ── Enviar pedido ────────────────────────────────────────── */

  async submitOrder() {
    const items = this.getItems();
    if (items.length === 0) return { ok: false, motivo: 'empty' };

    const payload = {
      items: items.map(i => ({
        sku:           i.sku,
        nombre:        i.product.nombre,
        presentacion:  i.product.presentacion,
        categoria:     i.product.categoria,
        es_controlado: i.product.es_controlado,
        qty:           i.qty,
        unidad_pedido: i.product.unidad_pedido,
      })),
    };

    const order = await storage.saveOrder(payload, this._session.id);
    this._items = [];
    // El carrito ya se vació en el server; sincronizamos estado local
    return { ok: true, order };
  },

  /* ── Repetir pedido ───────────────────────────────────────── */

  async repeatOrder(orderId) {
    const orders = await storage.getOrders(this._session.id);
    const order  = orderId ? orders.find(o => o.id === orderId) : orders[0];
    if (!order) return { ok: false, motivo: 'not_found' };

    const cargados = [];
    const omitidos = [];

    for (const item of order.items) {
      const result = await this.add(item.sku, item.qty);
      if (result.ok) {
        cargados.push({ sku: item.sku, nombre: item.nombre, qty: result.qty_final });
      } else {
        omitidos.push({ sku: item.sku, nombre: item.nombre, motivo: result.motivo });
      }
    }

    return { ok: true, cargados, omitidos };
  },

  /* ── Internos ─────────────────────────────────────────────── */

  _roundUp(qty, multiple) {
    if (multiple <= 1) return Math.max(1, qty);
    return Math.ceil(qty / multiple) * multiple;
  },

  async _persist() {
    await storage.saveCart({ items: this._items }, this._session.id);
  },
};

export default cart;
