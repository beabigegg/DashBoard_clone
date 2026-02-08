import { ensureMesApiAvailable } from '../core/api.js';
import {
  debounce,
  fetchWipAutocompleteItems,
} from '../core/autocomplete.js';
import { buildWipDetailQueryParams } from '../core/wip-derive.js';

ensureMesApiAvailable();

(function initWipDetailPage() {
          // ============================================================
          // State Management
          // ============================================================
          const state = {
              workcenter: '',
              data: null,
              packages: [],
              page: 1,
              pageSize: 100,
              filters: {
                  package: '',
                  type: '',
                  workorder: '',
                  lotid: ''
              },
              isLoading: false,
              refreshTimer: null,
              REFRESH_INTERVAL: 10 * 60 * 1000,  // 10 minutes
          };
  
          // WIP Status filter (separate from other filters)
          let activeStatusFilter = null;  // null | 'run' | 'queue' | 'quality-hold' | 'non-quality-hold'
  
          // AbortController for cancelling in-flight requests
          let tableAbortController = null;      // For loadTableOnly()
          let loadAllAbortController = null;    // For loadAllData()
  
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
              const formattedNew = formatNumber(newValue);
  
              if (oldValue !== formattedNew) {
                  el.textContent = formattedNew;
                  el.classList.add('updated');
                  setTimeout(() => el.classList.remove('updated'), 500);
              }
          }
  
          function getUrlParam(name) {
              const params = new URLSearchParams(window.location.search);
              return params.get(name) || '';
          }
  
          // ============================================================
          // API Functions (using MesApi)
          // ============================================================
          const API_TIMEOUT = 60000;  // 60 seconds timeout
  
          async function fetchPackages() {
              const result = await MesApi.get('/api/wip/meta/packages', { silent: true, timeout: API_TIMEOUT });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch packages');
          }
  
          async function fetchDetail(signal = null) {
              const params = buildWipDetailQueryParams({
                  page: state.page,
                  pageSize: state.pageSize,
                  filters: state.filters,
                  statusFilter: activeStatusFilter,
              });
  
              const result = await MesApi.get(`/api/wip/detail/${encodeURIComponent(state.workcenter)}`, {
                  params,
                  timeout: API_TIMEOUT,
                  signal
              });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch detail');
          }
  
          async function fetchWorkcenters() {
              const result = await MesApi.get('/api/wip/meta/workcenters', { silent: true, timeout: API_TIMEOUT });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch workcenters');
          }
  
          async function searchAutocompleteItems(type, query) {
              return fetchWipAutocompleteItems({
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
          }
  
          // ============================================================
          // Render Functions
          // ============================================================
          function renderSummary(summary) {
              if (!summary) return;
  
              updateElementWithTransition('totalLots', summary.totalLots);
              updateElementWithTransition('runLots', summary.runLots);
              updateElementWithTransition('queueLots', summary.queueLots);
              updateElementWithTransition('qualityHoldLots', summary.qualityHoldLots);
              updateElementWithTransition('nonQualityHoldLots', summary.nonQualityHoldLots);
          }
  
          function renderTable(data) {
              const container = document.getElementById('tableContainer');
  
              if (!data || !data.lots || data.lots.length === 0) {
                  container.innerHTML = '<div class="placeholder">No data available</div>';
                  document.getElementById('tableInfo').textContent = 'No data';
                  document.getElementById('pagination').style.display = 'none';
                  return;
              }
  
              const specs = data.specs || [];
  
              let html = '<table><thead><tr>';
              // Fixed columns
              html += '<th class="fixed-col">LOT ID</th>';
              html += '<th class="fixed-col">Equipment</th>';
              html += '<th class="fixed-col">WIP Status</th>';
              html += '<th class="fixed-col">Package</th>';
  
              // Spec columns
              specs.forEach(spec => {
                  html += `<th class="spec-col">${spec}</th>`;
              });
  
              html += '</tr></thead><tbody>';
  
              data.lots.forEach(lot => {
                  html += '<tr>';
  
                  // Fixed columns - LOT ID is clickable
                  const lotIdDisplay = lot.lotId
                      ? `<span class="lot-id-link" onclick="showLotDetail('${lot.lotId}')">${lot.lotId}</span>`
                      : '-';
                  html += `<td class="fixed-col">${lotIdDisplay}</td>`;
                  html += `<td class="fixed-col">${lot.equipment || '<span style="color: var(--muted);">-</span>'}</td>`;
  
                  // WIP Status with color and hold reason
                  const statusClass = `wip-status-${(lot.wipStatus || 'queue').toLowerCase()}`;
                  let statusText = lot.wipStatus || 'QUEUE';
                  if (lot.wipStatus === 'HOLD' && lot.holdReason) {
                      statusText = `HOLD (${lot.holdReason})`;
                  }
                  html += `<td class="fixed-col ${statusClass}">${statusText}</td>`;
  
                  html += `<td class="fixed-col">${lot.package || '-'}</td>`;
  
                  // Spec columns - show QTY in matching spec column
                  specs.forEach(spec => {
                      if (lot.spec === spec) {
                          html += `<td class="spec-cell has-data">${formatNumber(lot.qty)}</td>`;
                      } else {
                          html += '<td class="spec-cell"></td>';
                      }
                  });
  
                  html += '</tr>';
              });
  
              html += '</tbody></table>';
              container.innerHTML = html;
  
              // Update info
              const pagination = data.pagination;
              const start = (pagination.page - 1) * pagination.page_size + 1;
              const end = Math.min(pagination.page * pagination.page_size, pagination.total_count);
              document.getElementById('tableInfo').textContent =
                  `Showing ${start} - ${end} of ${formatNumber(pagination.total_count)}`;
  
              // Update pagination
              if (pagination.total_pages > 1) {
                  document.getElementById('pagination').style.display = 'flex';
                  document.getElementById('pageInfo').textContent =
                      `Page ${pagination.page} / ${pagination.total_pages}`;
                  document.getElementById('btnPrev').disabled = pagination.page <= 1;
                  document.getElementById('btnNext').disabled = pagination.page >= pagination.total_pages;
              } else {
                  document.getElementById('pagination').style.display = 'none';
              }
  
              // Update last update time
              if (data.sys_date) {
                  document.getElementById('lastUpdate').textContent = `Last Update: ${data.sys_date}`;
              }
          }
  
          function populatePackageFilter(packages) {
              const select = document.getElementById('filterPackage');
              const currentValue = select.value;
  
              select.innerHTML = '<option value="">All</option>';
              packages.forEach(pkg => {
                  const option = document.createElement('option');
                  option.value = pkg.name;
                  option.textContent = `${pkg.name} (${pkg.lot_count})`;
                  select.appendChild(option);
              });
  
              select.value = currentValue;
          }
  
          // ============================================================
          // Data Loading
          // ============================================================
          async function loadAllData(showOverlay = true) {
              // Cancel any in-flight request to prevent connection pile-up
              if (loadAllAbortController) {
                  loadAllAbortController.abort();
                  console.log('[WIP Detail] Previous request cancelled');
              }
              loadAllAbortController = new AbortController();
              const signal = loadAllAbortController.signal;
  
              state.isLoading = true;
  
              if (showOverlay) {
                  document.getElementById('loadingOverlay').style.display = 'flex';
              }
  
              // Show refresh indicator
              document.getElementById('refreshIndicator').classList.add('active');
              document.getElementById('refreshError').classList.remove('active');
              document.getElementById('refreshSuccess').classList.remove('active');
  
              try {
                  // Load packages for filter (non-blocking - don't fail if this times out)
                  if (state.packages.length === 0) {
                      try {
                          state.packages = await fetchPackages();
                          populatePackageFilter(state.packages);
                      } catch (pkgError) {
                          console.warn('Failed to load packages filter:', pkgError);
                      }
                  }
  
                  // Load detail data (main data - this is critical)
                  state.data = await fetchDetail(signal);
  
                  renderSummary(state.data.summary);
                  renderTable(state.data);
  
                  // Show success indicator
                  document.getElementById('refreshSuccess').classList.add('active');
                  setTimeout(() => {
                      document.getElementById('refreshSuccess').classList.remove('active');
                  }, 1500);
  
              } catch (error) {
                  // Ignore abort errors (expected when user triggers new request)
                  if (error.name === 'AbortError') {
                      console.log('[WIP Detail] Request cancelled (new request started)');
                      return;
                  }
                  console.error('Data load failed:', error);
                  document.getElementById('refreshError').classList.add('active');
              } finally {
                  state.isLoading = false;
                  document.getElementById('loadingOverlay').style.display = 'none';
                  document.getElementById('refreshIndicator').classList.remove('active');
              }
          }
  
          // ============================================================
          // Autocomplete Functions
          // ============================================================
          function showDropdown(dropdownId, items, onSelect) {
              const dropdown = document.getElementById(dropdownId);
              if (!items || items.length === 0) {
                  dropdown.innerHTML = '<div class="autocomplete-empty">No results</div>';
                  dropdown.classList.add('show');
                  return;
              }
              dropdown.innerHTML = items.map(item =>
                  `<div class="autocomplete-item" data-value="${item}">${item}</div>`
              ).join('');
              dropdown.classList.add('show');
  
              dropdown.querySelectorAll('.autocomplete-item').forEach(el => {
                  el.addEventListener('click', () => {
                      onSelect(el.dataset.value);
                      dropdown.classList.remove('show');
                  });
              });
          }
  
          function hideDropdown(dropdownId) {
              document.getElementById(dropdownId).classList.remove('show');
          }
  
          function showLoading(dropdownId) {
              const dropdown = document.getElementById(dropdownId);
              dropdown.innerHTML = '<div class="autocomplete-loading">Searching...</div>';
              dropdown.classList.add('show');
          }
  
          function setupAutocomplete(inputId, dropdownId, searchType) {
              const input = document.getElementById(inputId);
  
              const doSearch = debounce(async (query) => {
                  if (query.length < 2) {
                      hideDropdown(dropdownId);
                      return;
                  }
                  showLoading(dropdownId);
                  try {
                      const items = await searchAutocompleteItems(searchType, query);
                      showDropdown(dropdownId, items, (value) => {
                          input.value = value;
                      });
                  } catch (e) {
                      hideDropdown(dropdownId);
                  }
              }, 300);
  
              input.addEventListener('input', (e) => {
                  doSearch(e.target.value);
              });
  
              input.addEventListener('focus', (e) => {
                  if (e.target.value.length >= 2) {
                      doSearch(e.target.value);
                  }
              });
  
              // Hide dropdown when clicking outside
              document.addEventListener('click', (e) => {
                  if (!e.target.closest(`#${inputId}`) && !e.target.closest(`#${dropdownId}`)) {
                      hideDropdown(dropdownId);
                  }
              });
          }
  
          // ============================================================
          // Status Filter Toggle (Clickable Cards)
          // ============================================================
          function toggleStatusFilter(status) {
              if (activeStatusFilter === status) {
                  // Clicking the same card again removes the filter
                  activeStatusFilter = null;
              } else {
                  // Apply new filter
                  activeStatusFilter = status;
              }
  
              // Update card styles
              updateCardStyles();
  
              // Update table title
              updateTableTitle();
  
              // Reset to page 1 and reload table only (no isLoading guard)
              state.page = 1;
              loadTableOnly();
          }
  
          async function loadTableOnly() {
              // Cancel any in-flight request to prevent pile-up
              if (tableAbortController) {
                  tableAbortController.abort();
              }
              tableAbortController = new AbortController();
  
              // Show loading in table container
              const container = document.getElementById('tableContainer');
              container.innerHTML = '<div class="placeholder">Loading...</div>';
  
              // Show refresh indicator
              document.getElementById('refreshIndicator').classList.add('active');
  
              try {
                  state.data = await fetchDetail(tableAbortController.signal);
                  renderSummary(state.data.summary);
                  renderTable(state.data);
  
                  // Show success indicator
                  document.getElementById('refreshSuccess').classList.add('active');
                  setTimeout(() => {
                      document.getElementById('refreshSuccess').classList.remove('active');
                  }, 1500);
              } catch (error) {
                  // Ignore abort errors (expected when user clicks quickly)
                  if (error.name === 'AbortError') {
                      console.log('[WIP Detail] Table request cancelled (new filter selected)');
                      return;
                  }
                  console.error('Table load failed:', error);
                  container.innerHTML = '<div class="placeholder">Error loading data</div>';
                  document.getElementById('refreshError').classList.add('active');
              } finally {
                  document.getElementById('refreshIndicator').classList.remove('active');
              }
          }
  
          function updateCardStyles() {
              const row = document.getElementById('summaryRow');
              const statusCards = document.querySelectorAll('.summary-card.status-run, .summary-card.status-queue, .summary-card.status-quality-hold, .summary-card.status-non-quality-hold');
  
              // Remove active from all status cards
              statusCards.forEach(card => {
                  card.classList.remove('active');
              });
  
              if (activeStatusFilter) {
                  // Add filtering class to row (dims non-active cards)
                  row.classList.add('filtering');
  
                  // Add active to the selected card
                  const activeCard = document.querySelector(`.summary-card.status-${activeStatusFilter}`);
                  if (activeCard) {
                      activeCard.classList.add('active');
                  }
              } else {
                  // Remove filtering class
                  row.classList.remove('filtering');
              }
          }
  
          function updateTableTitle() {
              const titleEl = document.querySelector('.table-title');
              const baseTitle = 'Lot Details';
  
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
  
          // ============================================================
          // Filter & Pagination
          // ============================================================
          function applyFilters() {
              state.filters.workorder = document.getElementById('filterWorkorder').value.trim();
              state.filters.lotid = document.getElementById('filterLotid').value.trim();
              state.filters.package = document.getElementById('filterPackage').value.trim();
              state.filters.type = document.getElementById('filterType').value.trim();
              state.page = 1;
              loadAllData(false);
          }
  
          function clearFilters() {
              document.getElementById('filterWorkorder').value = '';
              document.getElementById('filterLotid').value = '';
              document.getElementById('filterPackage').value = '';
              document.getElementById('filterType').value = '';
              state.filters = { package: '', type: '', workorder: '', lotid: '' };
  
              // Also clear status filter
              activeStatusFilter = null;
              updateCardStyles();
              updateTableTitle();
  
              state.page = 1;
              loadAllData(false);
          }
  
          function prevPage() {
              if (state.page > 1) {
                  state.page--;
                  loadAllData(false);
              }
          }
  
          function nextPage() {
              if (state.data && state.page < state.data.pagination.total_pages) {
                  state.page++;
                  loadAllData(false);
              }
          }
  
          // ============================================================
          // Auto-refresh
          // ============================================================
          function startAutoRefresh() {
              if (state.refreshTimer) {
                  clearInterval(state.refreshTimer);
              }
              state.refreshTimer = setInterval(() => {
                  if (!document.hidden) {
                      loadAllData(false);
                  }
              }, state.REFRESH_INTERVAL);
          }
  
          function manualRefresh() {
              startAutoRefresh();
              loadAllData(false);
          }
  
          // ============================================================
          // Lot Detail Functions
          // ============================================================
          let selectedLotId = null;
  
          async function fetchLotDetail(lotId) {
              const result = await MesApi.get(`/api/wip/lot/${encodeURIComponent(lotId)}`, {
                  timeout: API_TIMEOUT
              });
              if (result.success) {
                  return result.data;
              }
              throw new Error(result.error || 'Failed to fetch lot detail');
          }
  
          async function showLotDetail(lotId) {
              // Update selected state
              selectedLotId = lotId;
  
              // Highlight the selected row
              document.querySelectorAll('.lot-id-link').forEach(el => {
                  el.classList.toggle('active', el.textContent === lotId);
              });
  
              // Show panel
              const panel = document.getElementById('lotDetailPanel');
              panel.classList.add('show');
  
              // Update title
              document.getElementById('lotDetailLotId').textContent = lotId;
  
              // Show loading
              document.getElementById('lotDetailContent').innerHTML = `
                  <div class="lot-detail-loading">
                      <span class="loading-spinner"></span>Loading...
                  </div>
              `;
  
              // Scroll to panel
              panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  
              try {
                  const data = await fetchLotDetail(lotId);
                  renderLotDetail(data);
              } catch (error) {
                  console.error('Failed to load lot detail:', error);
                  document.getElementById('lotDetailContent').innerHTML = `
                      <div class="lot-detail-loading" style="color: var(--danger);">
                          載入失敗：${error.message || '未知錯誤'}
                      </div>
                  `;
              }
          }
  
          function renderLotDetail(data) {
              const labels = data.fieldLabels || {};
  
              // Helper to format value
              const formatValue = (value) => {
                  if (value === null || value === undefined || value === '') {
                      return '<span class="empty">-</span>';
                  }
                  if (typeof value === 'number') {
                      return formatNumber(value);
                  }
                  return value;
              };
  
              // Helper to create field HTML
              const field = (key, customLabel = null) => {
                  const label = customLabel || labels[key] || key;
                  const value = data[key];
                  let valueClass = '';
  
                  // Special styling for WIP Status
                  if (key === 'wipStatus') {
                      valueClass = `status-${(value || '').toLowerCase()}`;
                  }
  
                  return `
                      <div class="lot-detail-field">
                          <span class="lot-detail-label">${label}</span>
                          <span class="lot-detail-value ${valueClass}">${formatValue(value)}</span>
                      </div>
                  `;
              };
  
              const html = `
                  <div class="lot-detail-grid">
                      <!-- Basic Info -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">基本資訊</div>
                          ${field('lotId')}
                          ${field('workorder')}
                          ${field('wipStatus')}
                          ${field('status')}
                          ${field('qty')}
                          ${field('qty2')}
                          ${field('ageByDays')}
                          ${field('priority')}
                      </div>
  
                      <!-- Product Info -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">產品資訊</div>
                          ${field('product')}
                          ${field('productLine')}
                          ${field('packageLef')}
                          ${field('pjType')}
                          ${field('pjFunction')}
                          ${field('bop')}
                          ${field('dateCode')}
                          ${field('produceRegion')}
                      </div>
  
                      <!-- Process Info -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">製程資訊</div>
                          ${field('workcenterGroup')}
                          ${field('workcenter')}
                          ${field('spec')}
                          ${field('specSequence')}
                          ${field('workflow')}
                          ${field('equipment')}
                          ${field('equipmentCount')}
                          ${field('location')}
                      </div>
  
                      <!-- Material Info -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">物料資訊</div>
                          ${field('waferLotId')}
                          ${field('waferPn')}
                          ${field('waferLotPrefix')}
                          ${field('leadframeName')}
                          ${field('leadframeOption')}
                          ${field('compoundName')}
                          ${field('dieConsumption')}
                          ${field('uts')}
                      </div>
  
                      <!-- Hold Info (if HOLD status) -->
                      ${data.wipStatus === 'HOLD' || data.holdCount > 0 ? `
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">Hold 資訊</div>
                          ${field('holdReason')}
                          ${field('holdCount')}
                          ${field('holdEmp')}
                          ${field('holdDept')}
                          ${field('holdComment')}
                          ${field('releaseTime')}
                          ${field('releaseEmp')}
                          ${field('releaseComment')}
                      </div>
                      ` : ''}
  
                      <!-- NCR Info (if exists) -->
                      ${data.ncrId ? `
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">NCR 資訊</div>
                          ${field('ncrId')}
                          ${field('ncrDate')}
                      </div>
                      ` : ''}
  
                      <!-- Comments -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">備註資訊</div>
                          ${field('comment')}
                          ${field('commentDate')}
                          ${field('commentEmp')}
                          ${field('futureHoldComment')}
                      </div>
  
                      <!-- Other Info -->
                      <div class="lot-detail-section">
                          <div class="lot-detail-section-title">其他資訊</div>
                          ${field('owner')}
                          ${field('startDate')}
                          ${field('tmttRemaining')}
                          ${field('dataUpdateDate')}
                      </div>
                  </div>
              `;
  
              document.getElementById('lotDetailContent').innerHTML = html;
          }
  
          function closeLotDetail() {
              const panel = document.getElementById('lotDetailPanel');
              panel.classList.remove('show');
  
              // Remove highlight from selected row
              document.querySelectorAll('.lot-id-link').forEach(el => {
                  el.classList.remove('active');
              });
  
              selectedLotId = null;
          }
  
          // ============================================================
          // Initialize
          // ============================================================
          async function init() {
              // Setup autocomplete for WORKORDER, LOT ID, PACKAGE, and TYPE
              setupAutocomplete('filterWorkorder', 'workorderDropdown', 'workorder');
              setupAutocomplete('filterLotid', 'lotidDropdown', 'lotid');
              setupAutocomplete('filterPackage', 'packageDropdown', 'package');
              setupAutocomplete('filterType', 'typeDropdown', 'type');
  
              // Allow Enter key to trigger filter
              document.getElementById('filterWorkorder').addEventListener('keypress', (e) => {
                  if (e.key === 'Enter') applyFilters();
              });
              document.getElementById('filterLotid').addEventListener('keypress', (e) => {
                  if (e.key === 'Enter') applyFilters();
              });
              document.getElementById('filterPackage').addEventListener('keypress', (e) => {
                  if (e.key === 'Enter') applyFilters();
              });
              document.getElementById('filterType').addEventListener('keypress', (e) => {
                  if (e.key === 'Enter') applyFilters();
              });
  
              // Get workcenter from URL or use first available
              state.workcenter = getUrlParam('workcenter');
  
              // Get filters from URL params (passed from wip_overview)
              const urlWorkorder = getUrlParam('workorder');
              const urlLotid = getUrlParam('lotid');
              const urlPackage = getUrlParam('package');
              const urlType = getUrlParam('type');
              if (urlWorkorder) {
                  state.filters.workorder = urlWorkorder;
                  document.getElementById('filterWorkorder').value = urlWorkorder;
              }
              if (urlLotid) {
                  state.filters.lotid = urlLotid;
                  document.getElementById('filterLotid').value = urlLotid;
              }
              if (urlPackage) {
                  state.filters.package = urlPackage;
                  document.getElementById('filterPackage').value = urlPackage;
              }
              if (urlType) {
                  state.filters.type = urlType;
                  document.getElementById('filterType').value = urlType;
              }
  
              if (!state.workcenter) {
                  // Fetch workcenters and use first one
                  try {
                      const workcenters = await fetchWorkcenters();
                      if (workcenters && workcenters.length > 0) {
                          state.workcenter = workcenters[0].name;
                          // Update URL without reload
                          window.history.replaceState({}, '', `/wip-detail?workcenter=${encodeURIComponent(state.workcenter)}`);
                      }
                  } catch (error) {
                      console.error('Failed to fetch workcenters:', error);
                  }
              }
  
              if (state.workcenter) {
                  document.getElementById('pageTitle').textContent = `WIP Detail - ${state.workcenter}`;
                  loadAllData(true);
                  startAutoRefresh();
  
                  // Handle page visibility (must be after workcenter is set)
                  document.addEventListener('visibilitychange', () => {
                      if (!document.hidden && state.workcenter) {
                          loadAllData(false);
                          startAutoRefresh();
                      }
                  });
              } else {
                  document.getElementById('tableContainer').innerHTML =
                      '<div class="placeholder">No workcenter available</div>';
                  document.getElementById('loadingOverlay').style.display = 'none';
              }
          }
  
          window.onload = init;

  Object.assign(window, {
    applyFilters,
    clearFilters,
    toggleStatusFilter,
    prevPage,
    nextPage,
    manualRefresh,
    showLotDetail,
    closeLotDetail,
    init
  });
})();
