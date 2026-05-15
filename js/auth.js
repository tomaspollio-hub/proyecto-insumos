/**
 * auth.js — autenticación y gestión de sesión.
 *
 * Etapa 2: valida contra POST /api/auth/login. Guarda JWT en sessionStorage.
 * El resto del código sigue llamando solo a auth.login / auth.logout /
 * auth.getSession / auth.requireAuth — contrato sin cambios.
 */

import storage from './storage.js';

const auth = {

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

    // Guardar token para que storage.js lo incluya en cada request
    sessionStorage.setItem('isumos_token', data.token);
    await storage.saveSession(data.session);
    return { ok: true, session: data.session };
  },

  async logout() {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    await storage.clearSession();
    window.location.href = './login.html';
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
    // Verificar que el token sigue en sessionStorage (se pierde al cerrar pestaña)
    const token = sessionStorage.getItem('isumos_token');
    if (!token) {
      await storage.clearSession();
      window.location.href = './login.html';
      return null;
    }
    return session;
  },
};

export default auth;
