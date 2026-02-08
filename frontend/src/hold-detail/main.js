import { ensureMesApiAvailable } from '../core/api.js';
import { escapeHtml, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();

(function initHoldDetailPage() {
          // ============================================================
          // State
          // ============================================================
          const state = {
              reason: new URLSearchParams(window.location.search).get('reason') || '',
              summary: null,
              distribution: null,
              lots: null,
              page: 1,
              perPage: 50,
              filters: {
                  workcenter: null,
                  package: null,
                  ageRange: null
              }
          };
  
          // ============================================================
          // Utility
          // ============================================================
          function formatNumber(num) {
              if (num === null || num === undefined || num === '-') return '-';
              return num.toLocaleString('zh-TW');
          }
  
          function jsSingleQuote(value) {
              return safeText(value, '')
                  .replace(/\\/g, '\\\\')
                  .replace(/'/g, "\\'");
          }
  
          // ============================================================
          // API Functions
          // ============================================================
          const API_TIMEOUT = 60000;
  
          async function fetchSummary() {
              const result = await MesApi.get('/api/wip/hold-detail/summary', {
                  params: { reason: state.reason },
                  timeout: API_TIMEOUT
              });
              if (result.success) return result.data;
              throw new Error(result.error);
          }
  
          async function fetchDistribution() {
              const result = await MesApi.get('/api/wip/hold-detail/distribution', {
                  params: { reason: state.reason },
                  timeout: API_TIMEOUT
              });
              if (result.success) return result.data;
              throw new Error(result.error);
          }
  
          async function fetchLots() {
              const params = {
                  reason: state.reason,
                  page: state.page,
                  per_page: state.perPage
              };
              if (state.filters.workcenter) params.workcenter = state.filters.workcenter;
              if (state.filters.package) params.package = state.filters.package;
              if (state.filters.ageRange) params.age_range = state.filters.ageRange;
  
              const result = await MesApi.get('/api/wip/hold-detail/lots', {
                  params,
                  timeout: API_TIMEOUT
              });
              if (result.success) return result.data;
              throw new Error(result.error);
          }
  
          // ============================================================
          // Render Functions
          // ============================================================
          function renderSummary(data) {
              document.getElementById('totalLots').textContent = formatNumber(data.totalLots);
              document.getElementById('totalQty').textContent = formatNumber(data.totalQty);
              document.getElementById('avgAge').textContent = data.avgAge ? `${data.avgAge}天` : '-';
              document.getElementById('maxAge').textContent = data.maxAge ? `${data.maxAge}天` : '-';
              document.getElementById('workcenterCount').textContent = formatNumber(data.workcenterCount);
          }
  
          function renderDistribution(data) {
              // Age distribution
              const ageMap = {};
              data.byAge.forEach(item => { ageMap[item.range] = item; });
  
              const age01 = ageMap['0-1'] || { lots: 0, qty: 0, percentage: 0 };
              const age13 = ageMap['1-3'] || { lots: 0, qty: 0, percentage: 0 };
              const age37 = ageMap['3-7'] || { lots: 0, qty: 0, percentage: 0 };
              const age7 = ageMap['7+'] || { lots: 0, qty: 0, percentage: 0 };
  
              document.getElementById('age01Lots').textContent = formatNumber(age01.lots);
              document.getElementById('age01Qty').textContent = formatNumber(age01.qty);
              document.getElementById('age01Pct').textContent = `${age01.percentage}%`;
  
              document.getElementById('age13Lots').textContent = formatNumber(age13.lots);
              document.getElementById('age13Qty').textContent = formatNumber(age13.qty);
              document.getElementById('age13Pct').textContent = `${age13.percentage}%`;
  
              document.getElementById('age37Lots').textContent = formatNumber(age37.lots);
              document.getElementById('age37Qty').textContent = formatNumber(age37.qty);
              document.getElementById('age37Pct').textContent = `${age37.percentage}%`;
  
              document.getElementById('age7Lots').textContent = formatNumber(age7.lots);
              document.getElementById('age7Qty').textContent = formatNumber(age7.qty);
              document.getElementById('age7Pct').textContent = `${age7.percentage}%`;
  
              // Workcenter table
              const wcBody = document.getElementById('workcenterBody');
              if (data.byWorkcenter.length === 0) {
                  wcBody.innerHTML = '<tr><td colspan="4" class="placeholder">No data</td></tr>';
              } else {
                  wcBody.innerHTML = data.byWorkcenter.map(item => `
                      <tr data-workcenter="${escapeHtml(safeText(item.name))}" onclick="toggleWorkcenterFilter('${jsSingleQuote(item.name)}')" class="${state.filters.workcenter === item.name ? 'active' : ''}">
                          <td>${escapeHtml(safeText(item.name))}</td>
                          <td>${escapeHtml(formatNumber(item.lots))}</td>
                          <td>${escapeHtml(formatNumber(item.qty))}</td>
                          <td>${escapeHtml(safeText(item.percentage, 0))}%</td>
                      </tr>
                  `).join('');
              }
  
              // Package table
              const pkgBody = document.getElementById('packageBody');
              if (data.byPackage.length === 0) {
                  pkgBody.innerHTML = '<tr><td colspan="4" class="placeholder">No data</td></tr>';
              } else {
                  pkgBody.innerHTML = data.byPackage.map(item => `
                      <tr data-package="${escapeHtml(safeText(item.name))}" onclick="togglePackageFilter('${jsSingleQuote(item.name)}')" class="${state.filters.package === item.name ? 'active' : ''}">
                          <td>${escapeHtml(safeText(item.name))}</td>
                          <td>${escapeHtml(formatNumber(item.lots))}</td>
                          <td>${escapeHtml(formatNumber(item.qty))}</td>
                          <td>${escapeHtml(safeText(item.percentage, 0))}%</td>
                      </tr>
                  `).join('');
              }
          }
  
          function renderLots(data) {
              const tbody = document.getElementById('lotBody');
              const lots = data.lots;
  
              if (lots.length === 0) {
                  tbody.innerHTML = '<tr><td colspan="10" class="placeholder">No data</td></tr>';
                  document.getElementById('tableInfo').textContent = 'No data';
                  document.getElementById('pagination').style.display = 'none';
                  return;
              }
  
              tbody.innerHTML = lots.map(lot => `
                  <tr>
                      <td>${escapeHtml(safeText(lot.lotId))}</td>
                      <td>${escapeHtml(safeText(lot.workorder))}</td>
                      <td>${escapeHtml(formatNumber(lot.qty))}</td>
                      <td>${escapeHtml(safeText(lot.package))}</td>
                      <td>${escapeHtml(safeText(lot.workcenter))}</td>
                      <td>${escapeHtml(safeText(lot.spec))}</td>
                      <td>${escapeHtml(safeText(lot.age))}天</td>
                      <td>${escapeHtml(safeText(lot.holdBy))}</td>
                      <td>${escapeHtml(safeText(lot.dept))}</td>
                      <td>${escapeHtml(safeText(lot.holdComment))}</td>
                  </tr>
              `).join('');
  
              // Update pagination
              const pg = data.pagination;
              const start = (pg.page - 1) * pg.perPage + 1;
              const end = Math.min(pg.page * pg.perPage, pg.total);
              document.getElementById('tableInfo').textContent = `顯示 ${start} - ${end} / ${formatNumber(pg.total)}`;
  
              if (pg.totalPages > 1) {
                  document.getElementById('pagination').style.display = 'flex';
                  document.getElementById('pageInfo').textContent = `Page ${pg.page} / ${pg.totalPages}`;
                  document.getElementById('btnPrev').disabled = pg.page <= 1;
                  document.getElementById('btnNext').disabled = pg.page >= pg.totalPages;
              } else {
                  document.getElementById('pagination').style.display = 'none';
              }
          }
  
          function updateFilterIndicator() {
              const indicator = document.getElementById('filterIndicator');
              const text = document.getElementById('filterText');
              const parts = [];
  
              if (state.filters.workcenter) parts.push(`Workcenter=${state.filters.workcenter}`);
              if (state.filters.package) parts.push(`Package=${state.filters.package}`);
              if (state.filters.ageRange) parts.push(`Age=${state.filters.ageRange}天`);
  
              if (parts.length > 0) {
                  text.textContent = '篩選: ' + parts.join(', ');
                  indicator.style.display = 'flex';
              } else {
                  indicator.style.display = 'none';
              }
  
              // Update active states
              document.querySelectorAll('.age-card').forEach(card => {
                  card.classList.toggle('active', card.dataset.range === state.filters.ageRange);
              });
              document.querySelectorAll('#workcenterBody tr').forEach(row => {
                  row.classList.toggle('active', row.dataset.workcenter === state.filters.workcenter);
              });
              document.querySelectorAll('#packageBody tr').forEach(row => {
                  row.classList.toggle('active', row.dataset.package === state.filters.package);
              });
          }
  
          // ============================================================
          // Filter Functions
          // ============================================================
          function toggleAgeFilter(range) {
              state.filters.ageRange = state.filters.ageRange === range ? null : range;
              state.page = 1;
              updateFilterIndicator();
              loadLots();
          }
  
          function toggleWorkcenterFilter(wc) {
              state.filters.workcenter = state.filters.workcenter === wc ? null : wc;
              state.page = 1;
              updateFilterIndicator();
              loadLots();
          }
  
          function togglePackageFilter(pkg) {
              state.filters.package = state.filters.package === pkg ? null : pkg;
              state.page = 1;
              updateFilterIndicator();
              loadLots();
          }
  
          function clearFilters() {
              state.filters = { workcenter: null, package: null, ageRange: null };
              state.page = 1;
              updateFilterIndicator();
              loadLots();
          }
  
          // ============================================================
          // Pagination
          // ============================================================
          function prevPage() {
              if (state.page > 1) {
                  state.page--;
                  loadLots();
              }
          }
  
          function nextPage() {
              if (state.lots && state.page < state.lots.pagination.totalPages) {
                  state.page++;
                  loadLots();
              }
          }
  
          // ============================================================
          // Data Loading
          // ============================================================
          async function loadLots() {
              document.getElementById('lotBody').innerHTML = '<tr><td colspan="10" class="placeholder">Loading...</td></tr>';
              document.getElementById('refreshIndicator').classList.add('active');
  
              try {
                  state.lots = await fetchLots();
                  renderLots(state.lots);
              } catch (error) {
                  console.error('Load lots failed:', error);
                  document.getElementById('lotBody').innerHTML = '<tr><td colspan="10" class="placeholder">Error loading data</td></tr>';
              } finally {
                  document.getElementById('refreshIndicator').classList.remove('active');
              }
          }
  
          async function loadAllData(showOverlay = true) {
              if (showOverlay) {
                  document.getElementById('loadingOverlay').style.display = 'flex';
              }
              document.getElementById('refreshIndicator').classList.add('active');
  
              try {
                  const [summary, distribution, lots] = await Promise.all([
                      fetchSummary(),
                      fetchDistribution(),
                      fetchLots()
                  ]);
  
                  state.summary = summary;
                  state.distribution = distribution;
                  state.lots = lots;
  
                  renderSummary(summary);
                  renderDistribution(distribution);
                  renderLots(lots);
                  updateFilterIndicator();
  
                  document.getElementById('lastUpdate').textContent = `Last Update: ${new Date().toLocaleString('zh-TW')}`;
              } catch (error) {
                  console.error('Load data failed:', error);
              } finally {
                  document.getElementById('loadingOverlay').style.display = 'none';
                  document.getElementById('refreshIndicator').classList.remove('active');
              }
          }
  
          function manualRefresh() {
              loadAllData(false);
          }
  
          // ============================================================
          // Initialize
          // ============================================================
          window.onload = function() {
              loadAllData(true);
          };

  Object.assign(window, {
    toggleAgeFilter,
    toggleWorkcenterFilter,
    togglePackageFilter,
    clearFilters,
    prevPage,
    nextPage,
    manualRefresh,
    loadAllData,
    loadLots
  });
})();
