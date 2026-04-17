/**
 * auth.js — autenticación y gestión de sesión.
 *
 * Hoy valida contra usuarios.json. Etapa 2: reemplazar login() por POST /api/auth/login.
 * El resto del código solo llama a auth.login / auth.logout / auth.getSession / auth.requireAuth.
 */

import storage from './storage.js';

const auth = {

  /**
   * Intenta autenticar al usuario contra usuarios.json.
   * @returns {{ ok: boolean, session?: object, motivo?: string }}
   */
  async login(usuario, password) {
    let usuarios;
    try {
      const res = await fetch('./usuarios.json');
      if (!res.ok) throw new Error('No se pudo cargar usuarios.json');
      usuarios = await res.json();
    } catch (err) {
      console.error('[auth] Error cargando usuarios:', err);
      return { ok: false, motivo: 'error_servidor' };
    }

    const match = usuarios.find(
      u => u.usuario === usuario && u.password === password
    );

    if (!match) return { ok: false, motivo: 'credenciales_invalidas' };

    const session = {
      id:       match.id,
      sucursal: match.sucursal,
      usuario:  match.usuario,
      rol:      match.rol,
    };

    await storage.saveSession(session);
    return { ok: true, session };
  },

  /** Cierra sesión y redirige al login. */
  async logout() {
    await storage.clearSession();
    window.location.href = './login.html';
  },

  /** Devuelve la sesión activa o null. */
  async getSession() {
    return storage.getSession();
  },

  /**
   * Guard de ruta. Redirige a login si no hay sesión activa.
   * @returns {object|null} sesión activa o null (tras redirigir)
   */
  async requireAuth() {
    const session = await storage.getSession();
    if (!session) {
      window.location.href = './login.html';
      return null;
    }
    return session;
  },
};

export default auth;
