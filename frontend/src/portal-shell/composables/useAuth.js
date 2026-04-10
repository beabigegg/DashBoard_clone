import { computed, ref } from 'vue';

const user = ref(null);
export const onlineCount = ref(null);
let _heartbeatTimer = null;

export const isAuthenticated = computed(() => user.value !== null);
export const isAdmin = computed(() => Boolean(user.value?.is_admin));

export function useAuth() {
  async function checkAuth() {
    try {
      const res = await fetch('/api/auth/me', { cache: 'no-store' });
      if (!res.ok) {
        user.value = null;
        return null;
      }
      const data = await res.json();
      user.value = data.data || null;
      return user.value;
    } catch {
      user.value = null;
      return null;
    }
  }

  async function login(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (data.success) {
      user.value = data.data;
      // Update CSRF meta tag with the rotated token from the server
      const newCsrf = data.data?.csrf_token;
      if (newCsrf) {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
          meta.setAttribute('content', newCsrf);
        }
      }
    }
    return data;
  }

  async function logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // ignore errors — clear session regardless
    }
    user.value = null;
    stopHeartbeat();
  }

  async function _sendHeartbeat() {
    try {
      const res = await fetch('/api/auth/heartbeat', { method: 'PATCH' });
      if (res.status === 401) {
        stopHeartbeat();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const count = data?.data?.online_count;
        if (typeof count === 'number') {
          onlineCount.value = count;
        }
      }
    } catch {
      // network error — keep timer, retry next interval
    }
  }

  function startHeartbeat() {
    if (_heartbeatTimer) return;
    _sendHeartbeat();
    _heartbeatTimer = setInterval(_sendHeartbeat, 5 * 60 * 1000);
  }

  function stopHeartbeat() {
    if (_heartbeatTimer) {
      clearInterval(_heartbeatTimer);
      _heartbeatTimer = null;
    }
  }

  return {
    user,
    isAuthenticated,
    isAdmin,
    onlineCount,
    checkAuth,
    login,
    logout,
    startHeartbeat,
    stopHeartbeat,
  };
}
