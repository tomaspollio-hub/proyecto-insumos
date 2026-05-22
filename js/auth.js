/**
 * auth.js — autenticación y gestión de sesión.
 */

import storage from './storage.js';

// ── Helpers JWT (sin dependencias externas) ───────────────────────────────────
function _decodeJwtPayload(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
  } catch { return null; }
}

function _tokenExp(token) {
  const p = _decodeJwtPayload(token);
  return p?.exp ?? null;   // segundos epoch
}

// ── Gestión del timer de renovación ──────────────────────────────────────────
let _refreshTimer   = null;
let _warningTimer   = null;
let _warningBanner  = null;
const WARN_BEFORE   = 5 * 60;   // avisar 5 min antes
const REFRESH_BEFORE = 2 * 60;  // renovar automáticamente 2 min antes

function _clearTimers() {
  clearTimeout(_refreshTimer);
  clearTimeout(_warningTimer);
  _hideBanner();
}

function _hideBanner() {
  if (_warningBanner) { _warningBanner.remove(); _warningBanner = null; }
}

function _showBanner() {
  if (_warningBanner) return;
  _warningBanner = document.createElement('div');
  _warningBanner.style.cssText = [
    'position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:9999',
    'background:#f59e0b;color:#fff;font-size:13px;font-weight:600',
    'padding:10px 20px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.2)',
    'display:flex;align-items:center;gap:12px',
  ].join(';');
  _warningBanner.innerHTML = `
    <span>⚠ Tu sesión vence en 5 minutos.</span>
    <button onclick="auth._doRefresh()" style="background:#fff;color:#f59e0b;border:none;border-radius:4px;padding:4px 10px;font-size:12px;font-weight:700;cursor:pointer">Renovar</button>
    <button onclick="this.closest('div').remove()" style="background:none;border:none;color:#fff;font-size:16px;cursor:pointer;padding:0 4px">✕</button>`;
  document.body.appendChild(_warningBanner);
}

function _scheduleTimers(token) {
  _clearTimers();
  const exp = _tokenExp(token);
  if (!exp) return;
  const now     = Math.floor(Date.now() / 1000);
  const ttl     = exp - now;
  if (ttl <= 0) return;
  const warnIn    = Math.max(0, (ttl - WARN_BEFORE)  * 1000);
  const refreshIn = Math.max(0, (ttl - REFRESH_BEFORE) * 1000);
  _warningTimer = setTimeout(_showBanner, warnIn);
  _refreshTimer = setTimeout(() => auth._doRefresh(), refreshIn);
}

const auth = {

  async _doRefresh() {
    const token = sessionStorage.getItem('isumos_token');
    if (!token) return;
    try {
      const res  = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.ok && data.token) {
        sessionStorage.setItem('isumos_token', data.token);
        _hideBanner();
        _scheduleTimers(data.token);
      }
    } catch { /* silencioso — el token simplemente vencerá */ }
  },

  async login(usuario, password) {
    let res;
    try {
      res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario, password }),
      });
    } catch {
      return { ok: false, motivo: 'error_servidor' };
    }

    const data = await res.json();
    if (!data.ok) return { ok: false, motivo: data.motivo };

    sessionStorage.setItem('isumos_token', data.token);
    await storage.saveSession(data.session);
    _scheduleTimers(data.token);
    return { ok: true, session: data.session };
  },

  async logout() {
    _clearTimers();
    try { await fetch('/api/auth/logout', { method: 'POST' }); } catch { /* silencio */ }
    try { await storage.clearSession(); } catch { /* silencio */ }
    localStorage.removeItem('isumos_session');
    sessionStorage.removeItem('isumos_token');
    window.location.replace('./login.html');
  },

  async getSession() {
    return storage.getSession();
  },

  async requireAuth() {
    const session = await storage.getSession();
    if (!session) {
      window.location.href = './login.html';
      return null;
    }
    const token = sessionStorage.getItem('isumos_token');
    if (!token) {
      await storage.clearSession();
      window.location.href = './login.html';
      return null;
    }
    // Verificar que el token no vencio ya
    const exp = _tokenExp(token);
    if (exp && Math.floor(Date.now() / 1000) >= exp) {
      await storage.clearSession();
      window.location.href = './login.html';
      return null;
    }
    _scheduleTimers(token);
    return session;
  },
};

// Exponer _doRefresh al scope global para el onclick del banner
window.auth = auth;

export default auth;
