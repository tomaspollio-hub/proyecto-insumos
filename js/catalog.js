/**
 * catalog.js — lógica de catálogo: carga, búsqueda, filtros por categoría.
 * Solo manipula estado. El render queda en catalog-view.js.
 */

import catalogView from './views/catalog-view.js';

const catalog = {
  _products:          [],
  _activeCategories:  new Set(),
  _searchQuery:       '',
  _cartAdd:           null,   /* fn(sku, qty) → Promise<result> — se inyecta desde index.html */

  async init() {
    let products;
    try {
      const res = await fetch('./productos.json');
      if (!res.ok) throw new Error('No se pudo cargar productos.json');
      products = await res.json();
    } catch (err) {
      console.error('[catalog] Error cargando productos:', err);
      catalogView.renderError('No se pudo cargar el catálogo. Recargá la página.');
      return;
    }

    this._products = products;

    const categories = [...new Set(products.map(p => p.categoria))].sort();
    catalogView.renderChips(categories, this._activeCategories, this._onChipClick.bind(this));

    this._render();
    catalogView.focusSearch();
  },

  onSearch(query) {
    this._searchQuery = query;
    this._render();
  },

  setCartAdd(fn) {
    this._cartAdd = fn;
  },

  async onEnter(query) {
    const trimmed = query.trim();
    if (!trimmed) return;

    const exact = this._products.find(p => p.codigo_barras === trimmed);
    if (!exact) return;

    if (this._cartAdd) {
      const result = await this._cartAdd(exact.sku_interno, exact.multiplo_minimo);
      if (result.ok) {
        const adj = result.ajustado ? ` (ajustado a múltiplo de ${exact.multiplo_minimo})` : '';
        catalogView.showToast(`Agregado: ${exact.nombre} — ${result.qty_final} ${exact.unidad_pedido}${adj}`);
      } else {
        const motivos = { sin_stock: 'sin stock', not_found: 'no encontrado' };
        catalogView.showToast(`No se pudo agregar ${exact.nombre}: ${motivos[result.motivo] ?? result.motivo}`);
      }
    } else {
      catalogView.showToast(`Producto detectado: ${exact.nombre} — pendiente conectar carrito`);
    }

    catalogView.clearSearch();
    this._searchQuery = '';
    this._render();
  },

  _onChipClick(categoria) {
    if (this._activeCategories.has(categoria)) {
      this._activeCategories.delete(categoria);
    } else {
      this._activeCategories.add(categoria);
    }
    catalogView.updateChips(this._activeCategories);
    this._render();
  },

  _getFiltered() {
    const q = this._searchQuery.trim().toLowerCase();

    return this._products.filter(p => {
      const matchesSearch =
        !q ||
        p.nombre.toLowerCase().includes(q) ||
        p.codigo_barras.startsWith(q) ||
        p.codigo_barras.includes(q);

      const matchesCategory =
        this._activeCategories.size === 0 ||
        this._activeCategories.has(p.categoria);

      return matchesSearch && matchesCategory;
    });
  },

  _render() {
    const filtered = this._getFiltered();
    catalogView.updateResultsCount(filtered.length, this._products.length);
    catalogView.renderGrid(filtered, this._onCardClick.bind(this));
  },

  _onCardClick(product) {
    const addFn = this._cartAdd
      ? async (sku, qty) => this._cartAdd(sku, qty)
      : null;
    catalogView.renderModal(product, addFn);
  },
};

export default catalog;
