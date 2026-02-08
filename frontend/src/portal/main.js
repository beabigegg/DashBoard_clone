import './portal.css';

(function initPortal() {
  const tabs = document.querySelectorAll('.tab');
  const frames = document.querySelectorAll('iframe');
  const toolFrame = document.getElementById('toolFrame');
  const healthDot = document.getElementById('healthDot');
  const healthLabel = document.getElementById('healthLabel');
  const healthPopup = document.getElementById('healthPopup');
  const healthStatus = document.getElementById('healthStatus');
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

  function setFrameHeight() {
    const header = document.querySelector('.header');
    const tabArea = document.querySelector('.tabs');
    if (!header || !tabArea) return;
    const height = Math.max(600, window.innerHeight - header.offsetHeight - tabArea.offsetHeight - 60);
    frames.forEach((frame) => {
      frame.style.height = `${height}px`;
    });
  }

  function activateTab(targetId) {
    tabs.forEach((tab) => tab.classList.remove('active'));
    frames.forEach((frame) => frame.classList.remove('active'));

    const tabBtn = document.querySelector(`[data-target="${targetId}"]`);
    const targetFrame = document.getElementById(targetId);

    if (tabBtn) tabBtn.classList.add('active');
    if (targetFrame) {
      targetFrame.classList.add('active');
      if (targetFrame.dataset.src && !targetFrame.src) {
        targetFrame.src = targetFrame.dataset.src;
      }
    }
  }

  function openTool(path) {
    if (!toolFrame) return false;
    tabs.forEach((tab) => tab.classList.remove('active'));
    frames.forEach((frame) => frame.classList.remove('active'));
    toolFrame.classList.add('active');
    if (toolFrame.src !== path) {
      toolFrame.src = path;
    }
    return false;
  }

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
          resourceCacheEnabled.style.color = resCache.loaded ? '#22c55e' : '#f59e0b';
        }
        if (resourceCacheCount) resourceCacheCount.textContent = resCache.count ? `${resCache.count} 筆` : '--';
        if (resourceCacheUpdatedAt) resourceCacheUpdatedAt.textContent = formatDateTime(resCache.updated_at);
      } else {
        if (resourceCacheEnabled) {
          resourceCacheEnabled.textContent = '未啟用';
          resourceCacheEnabled.style.color = '#9ca3af';
        }
        if (resourceCacheCount) resourceCacheCount.textContent = '--';
        if (resourceCacheUpdatedAt) resourceCacheUpdatedAt.textContent = '--';
      }

      const routeCache = data.route_cache || {};
      if (routeCacheMode) {
        routeCacheMode.textContent = routeCache.mode || '--';
      }
      if (routeCacheHitRate) {
        const l1 = routeCache.l1_hit_rate ?? '--';
        const l2 = routeCache.l2_hit_rate ?? '--';
        routeCacheHitRate.textContent = `${l1} / ${l2}`;
      }
      if (routeCacheDegraded) {
        routeCacheDegraded.textContent = routeCache.degraded ? '是' : '否';
        routeCacheDegraded.style.color = routeCache.degraded ? '#f59e0b' : '#22c55e';
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

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => activateTab(tab.dataset.target));
  });

  if (tabs.length > 0) {
    activateTab(tabs[0].dataset.target);
  }

  window.openTool = openTool;
  window.toggleHealthPopup = toggleHealthPopup;
  if (healthStatus) {
    healthStatus.addEventListener('click', toggleHealthPopup);
  }
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#healthStatus') && !e.target.closest('#healthPopup') && healthPopup) {
      healthPopup.classList.remove('show');
    }
  });

  checkHealth();
  setInterval(checkHealth, 30000);
  window.addEventListener('resize', setFrameHeight);
  setFrameHeight();
})();
