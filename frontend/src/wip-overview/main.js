import { ensureMesApiAvailable } from '../core/api.js';
import {
  debounce,
  fetchWipAutocompleteItems,
} from '../core/autocomplete.js';
import {
  buildWipOverviewQueryParams,
  splitHoldByType as splitHoldByTypeShared,
  prepareParetoData as prepareParetoDataShared,
} from '../core/wip-derive.js';

ensureMesApiAvailable();

(function initWipOverviewPage() {
          // ============================================================
          // State Management
          // ============================================================
          const state = {
              summary: null,
              matrix: null,
              hold: null,
              isLoading: false,
              lastError: false,
              refreshTimer: null,
              REFRESH_INTERVAL: 10 * 60 * 1000,  // 10 minutes
              filters: {
                  workorder: '',
                  lotid: '',
                  package: '',
                  type: ''
              }
          };
  
          // Status filter state (null = no filter, 'run'/'queue'/'hold' = filtered)
          let activeStatusFilter = null;
  
          // AbortController for cancelling in-flight requests
          let matrixAbortController = null;      // For loadMatrixOnly()
          let loadAllAbortController = null;     // For loadAllData()
  
          // ============================================================
          // Utility Functions
          // ============================================================
          function formatNumber(num) {
              if (num === null || num === undefined || num === '-') return '-';
              return num.toLocaleString('zh-TW');
          }
  
          function updateElementWithTransition(elementId, newValue) {
              const el = document.getElementById(elementId);
              const oldValue = el.textContent;
              let formattedNew;
              if (typeof newValue === 'number') {
                  formattedNew = formatNumber(newValue);
              } else if (newValue === null || newValue === undefined) {
                  formattedNew = '-';
              } else {
                  formattedNew = newValue;
              }
  
              if (oldValue !== formattedNew) {
                  el.textContent = formattedNew;
                  el.classList.add('updated');
                  setTimeout(() => el.classList.remove('updated'), 500);
              }
          }
  
          function buildQueryParams() {
              return buildWipOverviewQueryParams(state.filters);
          }
  
          // ============================================================
          // API Functions (using MesApi)
          // ============================================================
          const API_TIMEOUT = 60000;  // 60 seconds timeout
  
          async function fetchSummary(signal = null) {
              const params = buildQueryParams();
              const result = await MesApi.get('/api/wip/overview/summary', {
                  params,
                  timeout: API_TIMEOUT,
                  signal
              });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch summary');
          }
  
          async function fetchMatrix(signal = null) {
              const params = buildWipOverviewQueryParams(state.filters, activeStatusFilter);
              const result = await MesApi.get('/api/wip/overview/matrix', {
                  params,
                  timeout: API_TIMEOUT,
                  signal
              });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch matrix');
          }
  
          async function fetchHold(signal = null) {
              const params = buildQueryParams();
              const result = await MesApi.get('/api/wip/overview/hold', {
                  params,
                  timeout: API_TIMEOUT,
                  signal
              });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch hold');
          }
  
          // ============================================================
          // Autocomplete Functions
          // ============================================================
          async function searchAutocomplete(type, query) {
              const loadingEl = document.getElementById(`${type}Loading`);
              loadingEl.classList.add('active');
              try {
                  return await fetchWipAutocompleteItems({
                      searchType: type,
                      query,
                      filters: {
                          workorder: document.getElementById('filterWorkorder').value,
                          lotid: document.getElementById('filterLotid').value,
                          package: document.getElementById('filterPackage').value,
                          type: document.getElementById('filterType').value,
                      },
                      request: (url, options) => MesApi.get(url, options),
                  });
              } catch (error) {
                  console.error(`Search ${type} failed:`, error);
              } finally {
                  loadingEl.classList.remove('active');
              }
              return [];
          }
  
          function showDropdown(type, items) {
              const dropdown = document.getElementById(`${type}Dropdown`);
  
              if (items.length === 0) {
                  dropdown.innerHTML = '<div class="autocomplete-item no-results">無符合結果</div>';
              } else {
                  dropdown.innerHTML = items.map(item =>
                      `<div class="autocomplete-item" onclick="selectAutocomplete('${type}', '${item}')">${item}</div>`
                  ).join('');
              }
              dropdown.classList.add('active');
          }
  
          function hideDropdown(type) {
              const dropdown = document.getElementById(`${type}Dropdown`);
              dropdown.classList.remove('active');
          }
  
          function selectAutocomplete(type, value) {
              const input = document.getElementById(`filter${type.charAt(0).toUpperCase() + type.slice(1)}`);
              input.value = value;
              hideDropdown(type);
          }
  
          // Setup autocomplete for inputs
          function setupAutocomplete(type) {
              const input = document.getElementById(`filter${type.charAt(0).toUpperCase() + type.slice(1)}`);
  
              const debouncedSearch = debounce(async (query) => {
                  if (query.length >= 2) {
                      const items = await searchAutocomplete(type, query);
                      showDropdown(type, items);
                  } else {
                      hideDropdown(type);
                  }
              }, 300);
  
              input.addEventListener('input', (e) => {
                  debouncedSearch(e.target.value);
              });
  
              input.addEventListener('focus', async () => {
                  const query = input.value;
                  if (query.length >= 2) {
                      const items = await searchAutocomplete(type, query);
                      showDropdown(type, items);
                  }
              });
  
              input.addEventListener('blur', () => {
                  // Delay hide to allow click on dropdown
                  setTimeout(() => hideDropdown(type), 200);
              });
  
              input.addEventListener('keydown', (e) => {
                  if (e.key === 'Enter') {
                      hideDropdown(type);
                      applyFilters();
                  }
              });
          }
  
          // ============================================================
          // Filter Functions
          // ============================================================
          function applyFilters() {
              state.filters.workorder = document.getElementById('filterWorkorder').value.trim();
              state.filters.lotid = document.getElementById('filterLotid').value.trim();
              state.filters.package = document.getElementById('filterPackage').value.trim();
              state.filters.type = document.getElementById('filterType').value.trim();
  
              updateActiveFiltersDisplay();
              loadAllData(false);
          }
  
          function clearFilters() {
              document.getElementById('filterWorkorder').value = '';
              document.getElementById('filterLotid').value = '';
              document.getElementById('filterPackage').value = '';
              document.getElementById('filterType').value = '';
              state.filters.workorder = '';
              state.filters.lotid = '';
              state.filters.package = '';
              state.filters.type = '';
  
              updateActiveFiltersDisplay();
              loadAllData(false);
          }
  
          function removeFilter(type) {
              document.getElementById(`filter${type.charAt(0).toUpperCase() + type.slice(1)}`).value = '';
              state.filters[type] = '';
              updateActiveFiltersDisplay();
              loadAllData(false);
          }
  
          function updateActiveFiltersDisplay() {
              const container = document.getElementById('activeFilters');
              let html = '';
  
              if (state.filters.workorder) {
                  html += `<span class="filter-tag">WO: ${state.filters.workorder} <span class="remove" onclick="removeFilter('workorder')">×</span></span>`;
              }
              if (state.filters.lotid) {
                  html += `<span class="filter-tag">Lot: ${state.filters.lotid} <span class="remove" onclick="removeFilter('lotid')">×</span></span>`;
              }
              if (state.filters.package) {
                  html += `<span class="filter-tag">Pkg: ${state.filters.package} <span class="remove" onclick="removeFilter('package')">×</span></span>`;
              }
              if (state.filters.type) {
                  html += `<span class="filter-tag">Type: ${state.filters.type} <span class="remove" onclick="removeFilter('type')">×</span></span>`;
              }
  
              container.innerHTML = html;
          }
  
          // ============================================================
          // Render Functions
          // ============================================================
          function renderSummary(data) {
              if (!data) return;
  
              updateElementWithTransition('totalLots', data.totalLots);
              updateElementWithTransition('totalQty', data.totalQtyPcs);
  
              const ws = data.byWipStatus || {};
              const runLots = ws.run?.lots;
              const runQty = ws.run?.qtyPcs;
              const queueLots = ws.queue?.lots;
              const queueQty = ws.queue?.qtyPcs;
              const qualityHoldLots = ws.qualityHold?.lots;
              const qualityHoldQty = ws.qualityHold?.qtyPcs;
              const nonQualityHoldLots = ws.nonQualityHold?.lots;
              const nonQualityHoldQty = ws.nonQualityHold?.qtyPcs;
  
              updateElementWithTransition(
                  'runLots',
                  runLots === null || runLots === undefined ? '-' : `${formatNumber(runLots)} lots`
              );
              updateElementWithTransition(
                  'runQty',
                  runQty === null || runQty === undefined ? '-' : formatNumber(runQty)
              );
              updateElementWithTransition(
                  'queueLots',
                  queueLots === null || queueLots === undefined ? '-' : `${formatNumber(queueLots)} lots`
              );
              updateElementWithTransition(
                  'queueQty',
                  queueQty === null || queueQty === undefined ? '-' : formatNumber(queueQty)
              );
              updateElementWithTransition(
                  'qualityHoldLots',
                  qualityHoldLots === null || qualityHoldLots === undefined ? '-' : `${formatNumber(qualityHoldLots)} lots`
              );
              updateElementWithTransition(
                  'qualityHoldQty',
                  qualityHoldQty === null || qualityHoldQty === undefined ? '-' : formatNumber(qualityHoldQty)
              );
              updateElementWithTransition(
                  'nonQualityHoldLots',
                  nonQualityHoldLots === null || nonQualityHoldLots === undefined ? '-' : `${formatNumber(nonQualityHoldLots)} lots`
              );
              updateElementWithTransition(
                  'nonQualityHoldQty',
                  nonQualityHoldQty === null || nonQualityHoldQty === undefined ? '-' : formatNumber(nonQualityHoldQty)
              );
  
              if (data.dataUpdateDate) {
                  document.getElementById('lastUpdate').textContent = `Last Update: ${data.dataUpdateDate}`;
              }
          }
  
          // ============================================================
          // Status Filter Functions
          // ============================================================
          function toggleStatusFilter(status) {
              if (activeStatusFilter === status) {
                  // Deactivate filter
                  activeStatusFilter = null;
              } else {
                  // Activate new filter
                  activeStatusFilter = status;
              }
  
              updateCardStyles();
              updateMatrixTitle();
              loadMatrixOnly();
          }
  
          function updateCardStyles() {
              const row = document.querySelector('.wip-status-row');
              document.querySelectorAll('.wip-status-card').forEach(card => {
                  card.classList.remove('active');
              });
  
              if (activeStatusFilter) {
                  row.classList.add('filtering');
                  const activeCard = document.querySelector(`.wip-status-card.${activeStatusFilter}`);
                  if (activeCard) {
                      activeCard.classList.add('active');
                  }
              } else {
                  row.classList.remove('filtering');
              }
          }
  
          function updateMatrixTitle() {
              const titleEl = document.querySelector('.card-title');
              if (!titleEl) return;
  
              const baseTitle = 'Workcenter x Package Matrix (QTY)';
              if (activeStatusFilter) {
                  let statusLabel;
                  if (activeStatusFilter === 'quality-hold') {
                      statusLabel = '品質異常 Hold';
                  } else if (activeStatusFilter === 'non-quality-hold') {
                      statusLabel = '非品質異常 Hold';
                  } else {
                      statusLabel = activeStatusFilter.toUpperCase();
                  }
                  titleEl.textContent = `${baseTitle} - ${statusLabel} Only`;
              } else {
                  titleEl.textContent = baseTitle;
              }
          }
  
          async function loadMatrixOnly() {
              // Cancel any in-flight matrix request to prevent pile-up
              if (matrixAbortController) {
                  matrixAbortController.abort();
              }
              matrixAbortController = new AbortController();
  
              const container = document.getElementById('matrixContainer');
              container.innerHTML = '<div class="placeholder">Loading...</div>';
  
              try {
                  const matrix = await fetchMatrix(matrixAbortController.signal);
                  state.matrix = matrix;
                  renderMatrix(matrix);
              } catch (error) {
                  // Ignore abort errors (expected when user clicks quickly)
                  if (error.name === 'AbortError') {
                      console.log('[WIP Overview] Matrix request cancelled (new filter selected)');
                      return;
                  }
                  console.error('[WIP Overview] Matrix load failed:', error);
                  container.innerHTML = '<div class="placeholder">Error loading data</div>';
              }
          }
  
          function renderMatrix(data) {
              const container = document.getElementById('matrixContainer');
  
              if (!data || !data.workcenters || data.workcenters.length === 0) {
                  container.innerHTML = '<div class="placeholder">No data available</div>';
                  return;
              }
  
              // Limit packages to top 15 for display
              const displayPackages = data.packages.slice(0, 15);
  
              let html = '<table class="matrix-table"><thead><tr>';
              html += '<th>Workcenter</th>';
              displayPackages.forEach(pkg => {
                  html += `<th>${pkg}</th>`;
              });
              html += '<th class="total-col">Total</th>';
              html += '</tr></thead><tbody>';
  
              // Data rows
              data.workcenters.forEach(wc => {
                  html += '<tr>';
                  html += `<td class="clickable" onclick="navigateToDetail('${wc.replace(/'/g, "\\'")}')">${wc}</td>`;
  
                  displayPackages.forEach(pkg => {
                      const qty = data.matrix[wc]?.[pkg] || 0;
                      html += `<td>${qty ? formatNumber(qty) : '-'}</td>`;
                  });
  
                  html += `<td class="total-col">${formatNumber(data.workcenter_totals[wc] || 0)}</td>`;
                  html += '</tr>';
              });
  
              // Total row
              html += '<tr class="total-row">';
              html += '<td>Total</td>';
              displayPackages.forEach(pkg => {
                  html += `<td>${formatNumber(data.package_totals[pkg] || 0)}</td>`;
              });
              html += `<td class="total-col">${formatNumber(data.grand_total || 0)}</td>`;
              html += '</tr>';
  
              html += '</tbody></table>';
              container.innerHTML = html;
          }
  
          // ============================================================
          // Pareto Chart Functions
          // ============================================================
          let paretoCharts = {
              quality: null,
              nonQuality: null
          };
  
          // Task 2.1: Split hold data by type
          function splitHoldByType(data) {
              return splitHoldByTypeShared(data);
          }
  
          // Task 2.2: Prepare Pareto data (sort by QTY desc, calculate cumulative %)
          function prepareParetoData(items) {
              return prepareParetoDataShared(items);
          }
  
          // Task 3.1: Initialize Pareto charts
          function initParetoCharts() {
              const qualityEl = document.getElementById('qualityParetoChart');
              const nonQualityEl = document.getElementById('nonQualityParetoChart');
  
              if (qualityEl && !paretoCharts.quality) {
                  paretoCharts.quality = echarts.init(qualityEl);
              }
              if (nonQualityEl && !paretoCharts.nonQuality) {
                  paretoCharts.nonQuality = echarts.init(nonQualityEl);
              }
          }
  
          // Task 3.2: Render Pareto chart with ECharts
          function renderParetoChart(chart, paretoData, colorTheme) {
              if (!chart) return;
  
              const barColor = colorTheme === 'quality' ? '#ef4444' : '#f97316';
              const lineColor = colorTheme === 'quality' ? '#991B1B' : '#9A3412';
  
              const option = {
                  tooltip: {
                      trigger: 'axis',
                      axisPointer: { type: 'cross' },
                      formatter: function(params) {
                          const reason = params[0].name;
                          const qty = params[0].value;
                          const cumPct = params[1] ? params[1].value : 0;
                          return `<strong>${reason}</strong><br/>QTY: ${formatNumber(qty)}<br/>累計: ${cumPct}%`;
                      }
                  },
                  grid: {
                      left: '3%',
                      right: '4%',
                      bottom: '15%',
                      top: '10%',
                      containLabel: true
                  },
                  xAxis: {
                      type: 'category',
                      data: paretoData.reasons,
                      axisLabel: {
                          rotate: 30,
                          interval: 0,
                          fontSize: 10,
                          formatter: function(value) {
                              return value.length > 12 ? value.slice(0, 12) + '...' : value;
                          }
                      },
                      axisTick: { alignWithLabel: true }
                  },
                  yAxis: [
                      {
                          type: 'value',
                          name: 'QTY',
                          position: 'left',
                          axisLabel: {
                              formatter: function(val) {
                                  return val >= 1000 ? (val / 1000).toFixed(0) + 'k' : val;
                              }
                          }
                      },
                      {
                          type: 'value',
                          name: '累計%',
                          position: 'right',
                          min: 0,
                          max: 100,
                          axisLabel: { formatter: '{value}%' }
                      }
                  ],
                  series: [
                      {
                          name: 'QTY',
                          type: 'bar',
                          data: paretoData.qtys,
                          itemStyle: { color: barColor },
                          emphasis: {
                              itemStyle: { color: barColor, opacity: 0.8 }
                          }
                      },
                      {
                          name: '累計%',
                          type: 'line',
                          yAxisIndex: 1,
                          data: paretoData.cumulative,
                          symbol: 'circle',
                          symbolSize: 6,
                          lineStyle: { color: lineColor, width: 2 },
                          itemStyle: { color: lineColor }
                      }
                  ]
              };
  
              chart.setOption(option);
  
              // Task 3.3: Add click event for drill-down
              chart.off('click');  // Remove existing handlers
              chart.on('click', function(params) {
                  if (params.componentType === 'series' && params.seriesType === 'bar') {
                      const reason = paretoData.reasons[params.dataIndex];
                      if (reason && reason !== '未知') {
                          window.location.href = `/hold-detail?reason=${encodeURIComponent(reason)}`;
                      }
                  }
              });
          }
  
          // Task 4.1 & 4.2: Render Pareto table with drill-down links
          function renderParetoTable(containerId, paretoData) {
              const container = document.getElementById(containerId);
              if (!container) return;
  
              if (!paretoData.items || paretoData.items.length === 0) {
                  container.innerHTML = '';
                  return;
              }
  
              let html = '<table class="pareto-table"><thead><tr>';
              html += '<th>Hold Reason</th>';
              html += '<th>Lots</th>';
              html += '<th>QTY</th>';
              html += '<th>累計%</th>';
              html += '</tr></thead><tbody>';
  
              paretoData.items.forEach((item, idx) => {
                  const reason = item.reason || '未知';
                  const reasonLink = item.reason
                      ? `<a href="/hold-detail?reason=${encodeURIComponent(item.reason)}" class="reason-link">${reason}</a>`
                      : reason;
                  html += '<tr>';
                  html += `<td>${reasonLink}</td>`;
                  html += `<td>${formatNumber(item.lots)}</td>`;
                  html += `<td>${formatNumber(item.qty)}</td>`;
                  html += `<td class="cumulative">${paretoData.cumulative[idx]}%</td>`;
                  html += '</tr>';
              });
  
              html += '</tbody></table>';
              container.innerHTML = html;
          }
  
          // Task 3.4: Handle no data state
          function showParetoNoData(type, show) {
              const chartEl = document.getElementById(`${type}ParetoChart`);
              const noDataEl = document.getElementById(`${type}ParetoNoData`);
              if (chartEl) chartEl.style.display = show ? 'none' : 'block';
              if (noDataEl) noDataEl.style.display = show ? 'flex' : 'none';
          }
  
          // Main render function for Hold data
          function renderHold(data) {
              initParetoCharts();
  
              const { quality, nonQuality } = splitHoldByType(data);
              const qualityData = prepareParetoData(quality);
              const nonQualityData = prepareParetoData(nonQuality);
  
              // Update counts in header
              document.getElementById('qualityHoldCount').textContent = `${quality.length} 項`;
              document.getElementById('nonQualityHoldCount').textContent = `${nonQuality.length} 項`;
  
              // Quality Pareto
              if (quality.length > 0) {
                  showParetoNoData('quality', false);
                  renderParetoChart(paretoCharts.quality, qualityData, 'quality');
                  renderParetoTable('qualityParetoTable', qualityData);
              } else {
                  showParetoNoData('quality', true);
                  if (paretoCharts.quality) paretoCharts.quality.clear();
                  document.getElementById('qualityParetoTable').innerHTML = '';
              }
  
              // Non-Quality Pareto
              if (nonQuality.length > 0) {
                  showParetoNoData('nonQuality', false);
                  renderParetoChart(paretoCharts.nonQuality, nonQualityData, 'non-quality');
                  renderParetoTable('nonQualityParetoTable', nonQualityData);
              } else {
                  showParetoNoData('nonQuality', true);
                  if (paretoCharts.nonQuality) paretoCharts.nonQuality.clear();
                  document.getElementById('nonQualityParetoTable').innerHTML = '';
              }
          }
  
          // Task 5.3: Window resize handler for charts
          window.addEventListener('resize', function() {
              if (paretoCharts.quality) paretoCharts.quality.resize();
              if (paretoCharts.nonQuality) paretoCharts.nonQuality.resize();
          });
  
          // ============================================================
          // Navigation
          // ============================================================
          function navigateToDetail(workcenter) {
              const params = new URLSearchParams();
              params.append('workcenter', workcenter);
              if (state.filters.workorder) params.append('workorder', state.filters.workorder);
              if (state.filters.lotid) params.append('lotid', state.filters.lotid);
              if (state.filters.package) params.append('package', state.filters.package);
              if (state.filters.type) params.append('type', state.filters.type);
              window.location.href = `/wip-detail?${params.toString()}`;
          }
  
          // ============================================================
          // Data Loading
          // ============================================================
          async function loadAllData(showOverlay = true) {
              // Cancel any in-flight request to prevent connection pile-up
              if (loadAllAbortController) {
                  loadAllAbortController.abort();
                  console.log('[WIP Overview] Previous request cancelled');
              }
              loadAllAbortController = new AbortController();
              const signal = loadAllAbortController.signal;
  
              state.isLoading = true;
              console.log('[WIP Overview] Loading data...', showOverlay ? '(with overlay)' : '(background)');
  
              if (showOverlay) {
                  document.getElementById('loadingOverlay').style.display = 'flex';
              }
  
              // Show refresh indicator
              document.getElementById('refreshIndicator').classList.add('active');
              document.getElementById('refreshError').classList.remove('active');
              document.getElementById('refreshSuccess').classList.remove('active');
  
              try {
                  const startTime = performance.now();
                  const [summary, matrix, hold] = await Promise.all([
                      fetchSummary(signal),
                      fetchMatrix(signal),
                      fetchHold(signal)
                  ]);
                  const elapsed = Math.round(performance.now() - startTime);
  
                  state.summary = summary;
                  state.matrix = matrix;
                  state.hold = hold;
                  state.lastError = false;
  
                  renderSummary(summary);
                  renderMatrix(matrix);
                  renderHold(hold);
  
                  console.log(`[WIP Overview] Data loaded successfully in ${elapsed}ms`);
  
                  // Show success indicator
                  document.getElementById('refreshSuccess').classList.add('active');
                  setTimeout(() => {
                      document.getElementById('refreshSuccess').classList.remove('active');
                  }, 1500);
  
              } catch (error) {
                  // Ignore abort errors (expected when user triggers new request)
                  if (error.name === 'AbortError') {
                      console.log('[WIP Overview] Request cancelled (new request started)');
                      return;
                  }
                  console.error('[WIP Overview] Data load failed:', error);
                  state.lastError = true;
                  document.getElementById('refreshError').classList.add('active');
              } finally {
                  state.isLoading = false;
                  document.getElementById('loadingOverlay').style.display = 'none';
                  document.getElementById('refreshIndicator').classList.remove('active');
              }
          }
  
          // ============================================================
          // Auto-refresh
          // ============================================================
          function startAutoRefresh() {
              if (state.refreshTimer) {
                  clearInterval(state.refreshTimer);
              }
              console.log('[WIP Overview] Auto-refresh started, interval:', state.REFRESH_INTERVAL / 1000, 'seconds');
              state.refreshTimer = setInterval(() => {
                  if (!document.hidden) {
                      console.log('[WIP Overview] Auto-refresh triggered at', new Date().toLocaleTimeString());
                      loadAllData(false);  // Don't show overlay for auto-refresh
                  } else {
                      console.log('[WIP Overview] Auto-refresh skipped (tab hidden)');
                  }
              }, state.REFRESH_INTERVAL);
          }
  
          function manualRefresh() {
              // Reset timer on manual refresh
              startAutoRefresh();
              loadAllData(false);
          }
  
          // Handle page visibility
          document.addEventListener('visibilitychange', () => {
              if (!document.hidden) {
                  // Page became visible - refresh immediately
                  loadAllData(false);
                  startAutoRefresh();
              }
          });
  
          // ============================================================
          // Initialize
          // ============================================================
          window.onload = function() {
              setupAutocomplete('workorder');
              setupAutocomplete('lotid');
              setupAutocomplete('package');
              setupAutocomplete('type');
              loadAllData(true);
              startAutoRefresh();
          };

  Object.assign(window, {
    applyFilters,
    clearFilters,
    toggleStatusFilter,
    selectAutocomplete,
    removeFilter,
    navigateToDetail,
    manualRefresh,
    loadAllData,
    startAutoRefresh
  });
})();
