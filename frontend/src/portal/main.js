import './portal.css';

(function initPortal() {
  const sidebarItems = document.querySelectorAll('.sidebar-item[data-route]');
  const routeStatus = document.getElementById('routeStatus');
  const healthDot = document.getElementById('healthDot');
  const healthLabel = document.getElementById('healthLabel');
  const healthPopup = document.getElementById('healthPopup');
  const dbStatus = document.getElementById('dbStatus');
  const redisStatus = document.getElementById('redisStatus');
  const cacheEnabled = document.getElementById('cacheEnabled');
  const cacheSysDate = document.getElementById('cacheSysDate');
  const cacheUpdatedAt = document.getElementById('cacheUpdatedAt');
  const resourceCacheEnabled = document.getElementById('resourceCacheEnabled');
  const resourceCacheCount = document.getElementById('resourceCacheCount');
  const resourceCacheUpdatedAt = document.getElementById('resourceCacheUpdatedAt');
  const routeCacheMode = document.getElementById('routeCacheMode');
  const routeCacheHitRate = document.getElementById('routeCacheHitRate');
  const routeCacheDegraded = document.getElementById('routeCacheDegraded');

  function toggleHealthPopup() {
    if (!healthPopup) return;
    healthPopup.classList.toggle('show');
  }

  function formatStatus(status) {
    const icons = { ok: '✓', error: '✗', disabled: '○' };
    return icons[status] || status;
  }

  function setStatusClass(element, status) {
    if (!element) return;
    element.classList.remove('ok', 'error', 'disabled');
    element.classList.add(status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'disabled');
  }

  function formatDateTime(dateStr) {
    if (!dateStr) return '--';
    try {
      const date = new Date(dateStr);
      if (Number.isNaN(date.getTime())) return dateStr;
      return date.toLocaleString('zh-TW', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  }

  function markActiveSidebar() {
    const currentPath = window.location.pathname;
    sidebarItems.forEach((item) => {
      const route = item.dataset.route;
      if (route && route === currentPath) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });
  }

  async function checkHealth() {
    if (!healthDot || !healthLabel) return;
    try {
      const response = await fetch('/health', { cache: 'no-store' });
      const data = await response.json();

      healthDot.classList.remove('loading', 'healthy', 'degraded', 'unhealthy');
      if (data.status === 'healthy') {
        healthDot.classList.add('healthy');
        healthLabel.textContent = '連線正常';
      } else if (data.status === 'degraded') {
        healthDot.classList.add('degraded');
        healthLabel.textContent = '部分降級';
      } else {
        healthDot.classList.add('unhealthy');
        healthLabel.textContent = '連線異常';
      }

      const dbState = data.services?.database || 'error';
      if (dbStatus) dbStatus.innerHTML = `${formatStatus(dbState)} ${dbState === 'ok' ? '正常' : '異常'}`;
      setStatusClass(dbStatus, dbState);

      const redisState = data.services?.redis || 'disabled';
      const redisText = redisState === 'ok' ? '正常' : redisState === 'disabled' ? '未啟用' : '異常';
      if (redisStatus) redisStatus.innerHTML = `${formatStatus(redisState)} ${redisText}`;
      setStatusClass(redisStatus, redisState);

      const cache = data.cache || {};
      if (cacheEnabled) cacheEnabled.textContent = cache.enabled ? '已啟用' : '未啟用';
      if (cacheSysDate) cacheSysDate.textContent = cache.sys_date || '--';
      if (cacheUpdatedAt) cacheUpdatedAt.textContent = formatDateTime(cache.updated_at);

      const resCache = data.resource_cache || {};
      if (resCache.enabled) {
        if (resourceCacheEnabled) {
          resourceCacheEnabled.textContent = resCache.loaded ? '已載入' : '未載入';
          resourceCacheEnabled.style.color = resCache.loaded ? 'var(--color-token-h22c55e)' : 'var(--color-token-hf59e0b)';
        }
        if (resourceCacheCount) resourceCacheCount.textContent = resCache.count ? `${resCache.count} 筆` : '--';
        if (resourceCacheUpdatedAt) resourceCacheUpdatedAt.textContent = formatDateTime(resCache.updated_at);
      } else {
        if (resourceCacheEnabled) {
          resourceCacheEnabled.textContent = '未啟用';
          resourceCacheEnabled.style.color = 'var(--color-token-h9ca3af)';
        }
        if (resourceCacheCount) resourceCacheCount.textContent = '--';
        if (resourceCacheUpdatedAt) resourceCacheUpdatedAt.textContent = '--';
      }

      const routeCache = data.route_cache || {};
      if (routeCacheMode) routeCacheMode.textContent = routeCache.mode || '--';
      if (routeCacheHitRate) {
        const l1 = routeCache.l1_hit_rate ?? '--';
        const l2 = routeCache.l2_hit_rate ?? '--';
        routeCacheHitRate.textContent = `${l1} / ${l2}`;
      }
      if (routeCacheDegraded) {
        routeCacheDegraded.textContent = routeCache.degraded ? '是' : '否';
        routeCacheDegraded.style.color = routeCache.degraded ? 'var(--color-token-hf59e0b)' : 'var(--color-token-h22c55e)';
      }
    } catch (error) {
      console.error('Health check failed:', error);
      healthDot.classList.remove('loading', 'healthy', 'degraded');
      healthDot.classList.add('unhealthy');
      healthLabel.textContent = '無法連線';
      if (dbStatus) {
        dbStatus.innerHTML = '✗ 無法確認';
        setStatusClass(dbStatus, 'error');
      }
      if (redisStatus) {
        redisStatus.innerHTML = '✗ 無法確認';
        setStatusClass(redisStatus, 'error');
      }
    }
  }

  sidebarItems.forEach((item) => {
    item.addEventListener('click', () => {
      if (!routeStatus) return;
      routeStatus.classList.add('loading');
      routeStatus.textContent = `正在前往 ${item.dataset.pageName || item.dataset.route || '頁面'}...`;
    });
  });

  markActiveSidebar();
  window.toggleHealthPopup = toggleHealthPopup;

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#healthStatus') && !e.target.closest('#healthPopup') && healthPopup) {
      healthPopup.classList.remove('show');
    }
  });

  checkHealth();
  setInterval(checkHealth, 30000);
})();
