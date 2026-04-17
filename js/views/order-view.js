/**
 * order-view.js — vista de confirmar pedido, éxito e historial.
 */

function _esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString('es-AR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function _openOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.hidden = false;
  document.body.classList.add('modal-open');
  requestAnimationFrame(() => overlay.classList.add('is-open'));
  return overlay;
}

function _closeOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.classList.remove('is-open');
  document.body.classList.remove('modal-open');
  overlay.addEventListener('transitionend', () => { overlay.hidden = true; }, { once: true });
}

function _bindClose(overlayId, btnId, selfRef) {
  document.getElementById(btnId)?.addEventListener('click', () => selfRef.closeById(overlayId));
  document.getElementById(overlayId).addEventListener('click', e => {
    if (e.target.id === overlayId) selfRef.closeById(overlayId);
  });
  const onEsc = e => {
    if (e.key === 'Escape') { selfRef.closeById(overlayId); document.removeEventListener('keydown', onEsc); }
  };
  document.addEventListener('keydown', onEsc);
}

/* ── SVG icons (inline reutilizables) ──────────────────────── */
const ICON_CLOSE = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>`;
const ICON_SEND  = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5"/></svg>`;
const ICON_WARN  = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" clip-rule="evenodd"/></svg>`;
const ICON_REPEAT = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"/></svg>`;

const orderView = {

  closeById(id) { _closeOverlay(id); },

  /* ── Confirmar pedido ─────────────────────────────────────── */

  renderConfirm(items, summary, onSubmit) {
    const modal = document.getElementById('confirm-modal');

    /* agrupar por categoría */
    const byCategory = {};
    for (const item of items) {
      const cat = item.product.categoria;
      if (!byCategory[cat]) byCategory[cat] = [];
      byCategory[cat].push(item);
    }

    const hasControlled = items.some(i => i.product.es_controlado);

    modal.innerHTML = `
      <button class="modal__close" id="confirm-close" aria-label="Cerrar">${ICON_CLOSE}</button>
      <div class="modal__body">
        <h2 class="modal__title">Revisar pedido</h2>

        ${hasControlled ? `
        <div class="alert alert--warning">
          ${ICON_WARN}
          Este pedido contiene productos controlados — verificar recetas antes de despachar.
        </div>` : ''}

        <div class="confirm-items">
          ${Object.entries(byCategory).map(([cat, catItems]) => `
            <div class="confirm-category">
              <h3 class="confirm-category__title">${_esc(cat)}</h3>
              ${catItems.map(i => `
                <div class="confirm-row">
                  <span class="confirm-row__name">${_esc(i.product.nombre)}</span>
                  <span class="confirm-row__qty">${i.qty}
                    <span class="confirm-row__unit">${_esc(i.product.unidad_pedido)}</span>
                  </span>
                </div>`).join('')}
            </div>`).join('')}
        </div>

        <div class="confirm-summary">
          <span>${summary.total_items} producto${summary.total_items !== 1 ? 's' : ''}</span>
          <span class="confirm-summary__dot">·</span>
          <span>${summary.total_bultos} bulto${summary.total_bultos !== 1 ? 's' : ''}</span>
        </div>

        <button class="btn-submit-order" id="btn-submit-order">
          ${ICON_SEND} Enviar pedido
        </button>
      </div>`;

    _openOverlay('confirm-overlay');
    _bindClose('confirm-overlay', 'confirm-close', this);

    /* Anti-double-submit */
    let submitted = false;
    document.getElementById('btn-submit-order').addEventListener('click', async () => {
      if (submitted) return;
      submitted = true;
      const btn = document.getElementById('btn-submit-order');
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Enviando…';
      await onSubmit();
    });
  },

  closeConfirm() { _closeOverlay('confirm-overlay'); },

  /* ── Pedido enviado ───────────────────────────────────────── */

  renderSuccess(order) {
    const modal = document.getElementById('confirm-modal');
    modal.innerHTML = `
      <div class="modal__body modal__body--success">
        <div class="success-icon" aria-hidden="true">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
            <path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm13.36-1.814a.75.75 0 1 0-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 0 0-1.06 1.06l2.25 2.25a.75.75 0 0 0 1.14-.094l3.75-5.25Z" clip-rule="evenodd"/>
          </svg>
        </div>
        <h2 class="modal__title">Pedido enviado</h2>
        <p class="success-id">ID: <code>${_esc(order.id)}</code></p>
        <details class="order-json-wrap">
          <summary class="order-json-toggle">Ver JSON del pedido</summary>
          <pre class="order-json">${_esc(JSON.stringify(order, null, 2))}</pre>
        </details>
        <button class="btn-submit-order btn-submit-order--ok" id="btn-close-success">
          Volver al catálogo
        </button>
      </div>`;

    _openOverlay('confirm-overlay');
    document.getElementById('btn-close-success').addEventListener('click', () => {
      this.closeConfirm();
    });
  },

  /* ── Historial ────────────────────────────────────────────── */

  renderHistory(orders, onRepeat) {
    const modal = document.getElementById('history-modal');

    modal.innerHTML = `
      <button class="modal__close" id="history-close" aria-label="Cerrar">${ICON_CLOSE}</button>
      <div class="modal__body">
        <h2 class="modal__title">Historial de pedidos</h2>
        ${orders.length === 0
          ? '<p class="empty-state" style="padding:var(--space-10) 0">No hay pedidos anteriores.</p>'
          : `<div class="history-list">
              ${orders.map(order => {
                const totalBultos = order.items.reduce((s, i) => s + i.qty, 0);
                return `
                  <details class="history-order" data-order-id="${_esc(order.id)}">
                    <summary class="history-order__summary">
                      <div class="history-order__meta">
                        <span class="history-order__date">${_fmtDate(order.fecha)}</span>
                        <span class="history-order__stats">
                          ${order.items.length} prod. · ${totalBultos} bultos
                        </span>
                      </div>
                      <svg class="history-order__chevron" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5"/>
                      </svg>
                    </summary>
                    <div class="history-order__detail">
                      ${order.items.map(i => `
                        <div class="history-row">
                          <span class="history-row__name">${_esc(i.nombre)}</span>
                          <span class="history-row__qty">${i.qty}
                            <span class="history-row__unit">${_esc(i.unidad_pedido)}</span>
                          </span>
                        </div>`).join('')}
                      <button class="btn-repeat-order" data-order-id="${_esc(order.id)}">
                        ${ICON_REPEAT} Repetir este pedido
                      </button>
                    </div>
                  </details>`;
              }).join('')}
            </div>`}
      </div>`;

    _openOverlay('history-overlay');
    _bindClose('history-overlay', 'history-close', this);

    modal.querySelectorAll('.btn-repeat-order').forEach(btn => {
      btn.addEventListener('click', () => onRepeat(btn.dataset.orderId));
    });
  },

  closeHistory() { _closeOverlay('history-overlay'); },
};

export default orderView;
