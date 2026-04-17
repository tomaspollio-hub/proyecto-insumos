/**
 * catalog-view.js — renders del catálogo.
 * Sin lógica de negocio. Solo manipula el DOM según lo que le pasa catalog.js.
 */

const AVAIL_LABEL = {
  disponible: 'Disponible',
  consultar:  'Consultar',
  sin_stock:  'Sin stock',
};

const AVAIL_CLASS = {
  disponible: 'badge--available',
  consultar:  'badge--consult',
  sin_stock:  'badge--nostock',
};

const catalogView = {

  /* ── Chips ────────────────────────────────────────────────── */

  renderChips(categories, activeCategories, onChipClick) {
    const container = document.getElementById('category-chips');
    container.innerHTML = '';

    categories.forEach(cat => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip' + (activeCategories.has(cat) ? ' chip--active' : '');
      btn.textContent = cat;
      btn.dataset.category = cat;
      btn.addEventListener('click', () => onChipClick(cat));
      container.appendChild(btn);
    });
  },

  updateChips(activeCategories) {
    document.querySelectorAll('#category-chips .chip').forEach(btn => {
      btn.classList.toggle('chip--active', activeCategories.has(btn.dataset.category));
    });
  },

  /* ── Grid ─────────────────────────────────────────────────── */

  renderGrid(products, onCardClick) {
    const grid = document.getElementById('product-grid');

    if (products.length === 0) {
      grid.innerHTML = '<p class="empty-state">No se encontraron productos.</p>';
      return;
    }

    grid.innerHTML = products.map((p, i) => this._cardHTML(p, i)).join('');

    grid.querySelectorAll('.product-card').forEach((card, i) => {
      card.addEventListener('click', () => onCardClick(products[i]));
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onCardClick(products[i]);
        }
      });
    });
  },

  _cardHTML(p) {
    const availClass = AVAIL_CLASS[p.disponibilidad] ?? 'badge--nostock';
    const availLabel = AVAIL_LABEL[p.disponibilidad] ?? 'Sin stock';

    return `
      <article class="product-card" tabindex="0" role="listitem" aria-label="${this._esc(p.nombre)}">
        <div class="product-card__img-wrap">
          <img src="${this._esc(p.imagen)}"
               alt="${this._esc(p.nombre)}"
               class="product-card__img"
               onerror="this.src='assets/img/placeholder.svg';this.onerror=null;"
               loading="lazy" />
          ${p.es_controlado ? `
          <span class="product-card__controlled" title="Producto controlado — requiere receta">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd"
                d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
                clip-rule="evenodd"/>
            </svg>
            Controlado
          </span>` : ''}
        </div>
        <div class="product-card__body">
          <p class="product-card__category">${this._esc(p.categoria)}</p>
          <h2 class="product-card__name">${this._esc(p.nombre)}</h2>
          <p class="product-card__presentation">${this._esc(p.presentacion)}</p>
          <span class="availability-badge ${availClass}">${availLabel}</span>
        </div>
      </article>`;
  },

  /* ── Modal ────────────────────────────────────────────────── */

  renderModal(product, onAddToCart = null) {
    const isNoStock  = product.disponibilidad === 'sin_stock';
    const availClass = AVAIL_CLASS[product.disponibilidad] ?? 'badge--nostock';
    const availLabel = AVAIL_LABEL[product.disponibilidad] ?? 'Sin stock';

    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');

    content.innerHTML = `
      <button class="modal__close" id="modal-close" aria-label="Cerrar">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
             stroke-width="2" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
        </svg>
      </button>

      <div class="modal__img-wrap">
        <img src="${this._esc(product.imagen)}"
             alt="${this._esc(product.nombre)}"
             class="modal__img"
             onerror="this.src='assets/img/placeholder.svg';this.onerror=null;" />
        ${product.es_controlado ? `
        <span class="product-card__controlled" title="Producto controlado — requiere receta">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fill-rule="evenodd"
              d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
              clip-rule="evenodd"/>
          </svg>
          Producto controlado — requiere receta
        </span>` : ''}
      </div>

      <div class="modal__body">
        <p class="product-card__category">${this._esc(product.categoria)}</p>
        <h2 class="modal__name">${this._esc(product.nombre)}</h2>
        <p class="modal__presentation">${this._esc(product.presentacion)}</p>
        <p class="modal__description">${this._esc(product.descripcion)}</p>

        <div class="modal__meta">
          <span class="availability-badge ${availClass}">${availLabel}</span>
          <span class="modal__sku">${this._esc(product.sku_interno)}</span>
        </div>
        <div class="modal__meta">
          <span class="modal__label">Código de barras</span>
          <span class="modal__value">${this._esc(product.codigo_barras)}</span>
        </div>
        <div class="modal__meta">
          <span class="modal__label">Unidad de pedido</span>
          <span class="modal__value">${this._esc(product.unidad_pedido)}</span>
        </div>
        <div class="modal__meta">
          <span class="modal__label">Múltiplo mínimo</span>
          <span class="modal__value">${product.multiplo_minimo}</span>
        </div>

        <button class="btn-add-cart" ${isNoStock ? 'disabled aria-disabled="true"' : ''}>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
               stroke-width="2" stroke="currentColor" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round"
              d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.962-7.138a60.114 60.114 0 0 0-16.536-1.84M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z"/>
          </svg>
          ${isNoStock ? 'Sin stock' : 'Agregar al carrito'}
        </button>
      </div>
    `;

    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add('is-open'));
    document.body.classList.add('modal-open');

    const closeBtn = document.getElementById('modal-close');
    closeBtn.focus();

    const close = () => {
      overlay.classList.remove('is-open');
      overlay.addEventListener('transitionend', () => {
        overlay.hidden = true;
      }, { once: true });
      document.body.classList.remove('modal-open');
      this.focusSearch();
    };

    /* Botón agregar al carrito */
    if (onAddToCart && !isNoStock) {
      const addBtn = content.querySelector('.btn-add-cart');
      if (addBtn) {
        addBtn.addEventListener('click', async () => {
          addBtn.disabled = true;
          const result = await onAddToCart(product.sku_interno, product.multiplo_minimo);
          if (result.ok) {
            close();
            this.showToast(`Agregado: ${product.nombre} — ${result.qty_final} ${product.unidad_pedido}`);
          } else {
            addBtn.disabled = false;
            this.showToast(`Sin stock: ${product.nombre}`);
          }
        });
      }
    }

    closeBtn.addEventListener('click', close);

    overlay.addEventListener('click', e => {
      if (e.target === overlay) close();
    }, { once: true });

    const onEsc = e => {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onEsc); }
    };
    document.addEventListener('keydown', onEsc);
  },

  /* ── Toast ────────────────────────────────────────────────── */

  showToast(msg) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    container.appendChild(toast);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => toast.classList.add('toast--visible'));
    });

    setTimeout(() => {
      toast.classList.remove('toast--visible');
      toast.addEventListener('transitionend', () => toast.remove(), { once: true });
      this.focusSearch();
    }, 3500);
  },

  /* ── Results count ────────────────────────────────────────── */

  updateResultsCount(count, total) {
    const el = document.getElementById('results-count');
    if (!el) return;
    if (count === total) {
      el.textContent = `${total} producto${total !== 1 ? 's' : ''}`;
    } else {
      el.textContent = `${count} de ${total} producto${total !== 1 ? 's' : ''}`;
    }
  },

  /* ── Error ────────────────────────────────────────────────── */

  renderError(msg) {
    const grid = document.getElementById('product-grid');
    grid.innerHTML = `<p class="empty-state">${this._esc(msg)}</p>`;
  },

  /* ── Focus helpers ────────────────────────────────────────── */

  focusSearch() {
    const input = document.getElementById('search-input');
    if (input) input.focus();
  },

  clearSearch() {
    const input = document.getElementById('search-input');
    if (input) { input.value = ''; input.dispatchEvent(new Event('input')); }
  },

  /* ── Utils ────────────────────────────────────────────────── */

  _esc(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  },
};

export default catalogView;
