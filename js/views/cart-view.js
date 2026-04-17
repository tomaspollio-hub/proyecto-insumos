/**
 * cart-view.js — render del panel de carrito.
 * Sin lógica de negocio. Recibe callbacks del orquestador (index.html).
 */

const cartView = {
  _cb: {},

  init(callbacks) {
    this._cb = callbacks;
    this._bindStatic();
  },

  _bindStatic() {
    /* Mobile: tab toggle */
    document.getElementById('cart-tab').addEventListener('click', () => {
      document.getElementById('cart-panel').classList.toggle('is-open');
    });

    document.getElementById('cart-close').addEventListener('click', () => {
      document.getElementById('cart-panel').classList.remove('is-open');
    });

    /* Vaciar — confirmación de dos pasos */
    const clearBtn = document.getElementById('btn-clear-cart');
    let confirmPending = false;
    let confirmTimer   = null;

    clearBtn.addEventListener('click', () => {
      if (!confirmPending) {
        confirmPending = true;
        clearBtn.textContent = '¿Confirmar?';
        clearBtn.classList.add('is-confirm');
        confirmTimer = setTimeout(() => {
          confirmPending = false;
          clearBtn.textContent = 'Vaciar carrito';
          clearBtn.classList.remove('is-confirm');
        }, 3000);
      } else {
        clearTimeout(confirmTimer);
        confirmPending = false;
        clearBtn.textContent = 'Vaciar carrito';
        clearBtn.classList.remove('is-confirm');
        this._cb.onClear();
      }
    });

    document.getElementById('btn-review-order').addEventListener('click', () => {
      this._cb.onReview();
    });
  },

  /* ── Render principal ─────────────────────────────────────── */

  render(items, summary) {
    this._renderItems(items);
    this._renderSummary(summary);
    this._renderTab(summary);
    document.getElementById('cart-footer').hidden = items.length === 0;
  },

  _renderItems(items) {
    const container = document.getElementById('cart-items');

    if (items.length === 0) {
      container.innerHTML = '<p class="cart-empty">El carrito está vacío.</p>';
      return;
    }

    container.innerHTML = items.map(item => this._itemHTML(item)).join('');

    container.querySelectorAll('.cart-item').forEach((el, i) => {
      const item = items[i];
      const step = item.product.multiplo_minimo;

      el.querySelector('.btn-qty-minus').addEventListener('click', () =>
        this._cb.onUpdateQty(item.sku, -step));
      el.querySelector('.btn-qty-plus').addEventListener('click', () =>
        this._cb.onUpdateQty(item.sku, step));
      el.querySelector('.btn-item-remove').addEventListener('click', () =>
        this._cb.onRemove(item.sku));
    });
  },

  _itemHTML(item) {
    const p = item.product;
    const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    return `
      <div class="cart-item">
        <img class="cart-item__img"
             src="${e(p.imagen)}"
             onerror="this.src='assets/img/placeholder.svg';this.onerror=null;"
             alt="${e(p.nombre)}" />
        <div class="cart-item__info">
          <p class="cart-item__name">${e(p.nombre)}</p>
          <p class="cart-item__meta">${e(p.presentacion)}</p>
          <div class="cart-item__controls">
            <button class="btn-qty btn-qty-minus" aria-label="Reducir cantidad">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fill-rule="evenodd" d="M4 10a.75.75 0 0 1 .75-.75h10.5a.75.75 0 0 1 0 1.5H4.75A.75.75 0 0 1 4 10Z" clip-rule="evenodd"/>
              </svg>
            </button>
            <span class="cart-item__qty">${item.qty}</span>
            <button class="btn-qty btn-qty-plus" aria-label="Aumentar cantidad">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z"/>
              </svg>
            </button>
            <span class="cart-item__unit">${e(p.unidad_pedido)}</span>
          </div>
        </div>
        <button class="btn-item-remove" aria-label="Eliminar ${e(p.nombre)}">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fill-rule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z" clip-rule="evenodd"/>
          </svg>
        </button>
      </div>`;
  },

  _renderSummary(summary) {
    const el = document.getElementById('cart-summary');
    if (!el) return;
    const { total_items: ti, total_bultos: tb } = summary;
    el.textContent = ti === 0 ? '' :
      `${ti} producto${ti !== 1 ? 's' : ''} · ${tb} bulto${tb !== 1 ? 's' : ''}`;
  },

  _renderTab(summary) {
    const badge = document.getElementById('cart-badge');
    const tab   = document.getElementById('cart-tab');
    if (!badge || !tab) return;
    badge.textContent = summary.total_bultos;
    badge.hidden = summary.total_items === 0;
    tab.classList.toggle('has-items', summary.total_items > 0);
  },
};

export default cartView;
