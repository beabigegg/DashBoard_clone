import { ensureMesApiAvailable } from '../core/api.js';

ensureMesApiAvailable();

/**
 * Query Tool JavaScript
 *
 * Handles batch tracing and equipment period query functionality.
 */

// ============================================================
// State Management
// ============================================================

const QueryToolState = {
    // LOT query
    queryType: 'lot_id',
    resolvedLots: [],
    selectedLotIndex: 0,
    lotHistories: {},  // container_id -> history data
    lotAssociations: {},  // container_id -> { materials, rejects, holds, jobs }

    // Timeline
    timelineSelectedLots: new Set(),  // Set of indices for timeline display
    currentLotIndex: 0,  // For association highlight

    // Workcenter group filter
    workcenterGroups: [],  // All available groups [{name, sequence}]
    selectedWorkcenterGroups: new Set(),  // Selected group names for filtering

    // Equipment query
    allEquipments: [],
    selectedEquipments: new Set(),
    equipmentResults: null,
};

// Expose for debugging
window.QueryToolState = QueryToolState;

// ============================================================
// State Cleanup (Memory Management)
// ============================================================

/**
 * Clear all query state to free memory before new query or page unload.
 * This prevents browser memory issues with large datasets.
 */
function clearQueryState() {
    // Clear LOT query state
    QueryToolState.resolvedLots = [];
    QueryToolState.selectedLotIndex = 0;
    QueryToolState.lotHistories = {};
    QueryToolState.lotAssociations = {};
    QueryToolState.timelineSelectedLots = new Set();
    QueryToolState.currentLotIndex = 0;

    // Clear workcenter group selection (keep workcenterGroups as it's reused)
    QueryToolState.selectedWorkcenterGroups = new Set();

    // Hide selection bar (contains LOT selector and workcenter filter)
    const selectionBar = document.getElementById('selectionBar');
    if (selectionBar) selectionBar.style.display = 'none';

    // Clear equipment query state
    QueryToolState.equipmentResults = null;
    // Note: Keep allEquipments and selectedEquipments as they are reused

    // Clear global timeline data (can be large)
    if (window._timelineData) {
        window._timelineData.lotsData = [];
        window._timelineData.stationColors = {};
        window._timelineData.allStations = [];
        window._timelineData.selectedStations = new Set();
        window._timelineData = null;
    }

    // Close any open popups
    closeTimelinePopup();

    // Clear DOM content
    const lotResultsContent = document.getElementById('lotResultsContent');
    if (lotResultsContent) {
        lotResultsContent.innerHTML = '';
        lotResultsContent.style.display = 'none';
    }

    // Reset empty state visibility
    const lotEmptyState = document.getElementById('lotEmptyState');
    if (lotEmptyState) {
        lotEmptyState.style.display = 'block';
    }

    // Hide LOT info bar
    const lotInfoBar = document.getElementById('lotInfoBar');
    if (lotInfoBar) lotInfoBar.style.display = 'none';

    console.log('[QueryTool] State cleared for memory management');
}

// Clear state before page unload to help garbage collection
window.addEventListener('beforeunload', () => {
    clearQueryState();
});

// Expose for manual cleanup if needed
window.clearQueryState = clearQueryState;

// ============================================================
// Initialization
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    loadEquipments();
    loadWorkcenterGroups();  // Load workcenter groups for filtering
    setLast30Days();

    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        // Equipment dropdown
        const eqDropdown = document.getElementById('equipmentDropdown');
        const eqSelector = document.querySelector('.equipment-selector');
        if (eqSelector && !eqSelector.contains(e.target)) {
            eqDropdown.classList.remove('show');
        }

        // LOT selector dropdown
        const lotDropdown = document.getElementById('lotSelectorDropdown');
        const lotSelector = document.getElementById('lotSelectorContainer');
        if (lotSelector && !lotSelector.contains(e.target)) {
            lotDropdown.classList.remove('show');
        }

        // Workcenter group dropdown
        const wcDropdown = document.getElementById('wcGroupDropdown');
        const wcSelector = document.getElementById('workcenterGroupSelectorContainer');
        if (wcSelector && !wcSelector.contains(e.target)) {
            if (wcDropdown) wcDropdown.classList.remove('show');
        }
    });

    // Handle Enter key in search input
    const searchInput = document.getElementById('lotInputField');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                executeLotQuery();
            }
        });
    }
});

// ============================================================
// Query Mode Switching (Batch vs Equipment)
// ============================================================

function switchQueryMode(mode) {
    // Update tabs
    document.querySelectorAll('.query-mode-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });

    // Show/hide filter bars
    document.getElementById('batchFilterBar').style.display = mode === 'batch' ? 'flex' : 'none';
    document.getElementById('equipmentFilterBar').style.display = mode === 'equipment' ? 'flex' : 'none';

    // Show/hide results panels
    document.getElementById('batchResultsPanel').style.display = mode === 'batch' ? 'block' : 'none';
    document.getElementById('equipmentResultsPanel').style.display = mode === 'equipment' ? 'block' : 'none';

    // Hide LOT info bar when switching to equipment mode
    if (mode === 'equipment') {
        document.getElementById('lotInfoBar').style.display = 'none';
    }
}

// ============================================================
// Query Type Selection
// ============================================================

function setQueryType(type) {
    QueryToolState.queryType = type;

    // Update select element if called programmatically
    const select = document.getElementById('queryTypeSelect');
    if (select && select.value !== type) {
        select.value = type;
    }

    // Update input placeholder based on type
    const placeholders = {
        'lot_id': '輸入 LOT ID（多筆以逗號分隔）',
        'serial_number': '輸入流水號（多筆以逗號分隔）',
        'work_order': '輸入 GA工單（多筆以逗號分隔）',
    };

    const inputField = document.getElementById('lotInputField');
    if (inputField) {
        inputField.placeholder = placeholders[type] || placeholders['lot_id'];
    }
}

// ============================================================
// LOT Query Functions
// ============================================================

function parseInputValues(text) {
    // Parse input: split by newlines and commas, trim whitespace, filter empty
    return text
        .split(/[\n,]/)
        .map(s => s.trim())
        .filter(s => s.length > 0);
}

async function executeLotQuery() {
    const input = document.getElementById('lotInputField').value;
    const values = parseInputValues(input);

    if (values.length === 0) {
        Toast.error('請輸入查詢條件');
        return;
    }

    // Validate limits
    const limits = { 'lot_id': 50, 'serial_number': 50, 'work_order': 10 };
    const limit = limits[QueryToolState.queryType];
    if (values.length > limit) {
        Toast.error(`輸入數量超過上限 (${limit} 筆)`);
        return;
    }

    // Clear previous query state to free memory
    clearQueryState();

    // Show loading
    document.getElementById('lotEmptyState').style.display = 'none';
    document.getElementById('lotResultsContent').style.display = 'block';
    document.getElementById('lotResultsContent').innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <br>解析中...
        </div>
    `;

    // Hide LOT info bar and selection bar during loading
    document.getElementById('lotInfoBar').style.display = 'none';
    const selectionBar = document.getElementById('selectionBar');
    if (selectionBar) selectionBar.style.display = 'none';

    document.getElementById('lotQueryBtn').disabled = true;

    try {
        // Step 1: Resolve to CONTAINERID
        const resolveResult = await MesApi.post('/api/query-tool/resolve', {
            input_type: QueryToolState.queryType,
            values: values
        });

        if (resolveResult.error) {
            document.getElementById('lotResultsContent').innerHTML = `<div class="error">${resolveResult.error}</div>`;
            return;
        }

        if (!resolveResult.data || resolveResult.data.length === 0) {
            document.getElementById('lotResultsContent').innerHTML = `
                <div class="empty-state">
                    <p>查無符合的批次資料</p>
                    ${resolveResult.not_found && resolveResult.not_found.length > 0
                        ? `<p style="font-size: 12px; color: #888;">未找到: ${resolveResult.not_found.join(', ')}</p>`
                        : ''}
                </div>
            `;
            return;
        }

        QueryToolState.resolvedLots = resolveResult.data;
        QueryToolState.selectedLotIndex = 0;
        QueryToolState.lotHistories = {};
        QueryToolState.lotAssociations = {};

        // Initialize with empty selection - user must confirm
        QueryToolState.timelineSelectedLots = new Set();

        // Clear workcenter group selection for new query
        QueryToolState.selectedWorkcenterGroups = new Set();

        // Hide LOT info bar initially
        document.getElementById('lotInfoBar').style.display = 'none';

        // Show workcenter group selector for filtering
        showWorkcenterGroupSelector();

        if (resolveResult.data.length === 1) {
            // Single result - auto-select and show directly
            QueryToolState.timelineSelectedLots.add(0);
            // Hide LOT selector (not needed for single result), but show workcenter filter
            const lotSelector = document.getElementById('lotSelectorContainer');
            if (lotSelector) lotSelector.style.display = 'none';
            // Update hint for single LOT
            const hint = document.getElementById('selectionHint');
            if (hint) hint.innerHTML = '<span>選擇站點後點擊「套用篩選」重新載入</span>';
            // Load and show the single lot's data
            confirmLotSelection();
        } else {
            // Multiple results - show selector for user to choose
            const lotSelector = document.getElementById('lotSelectorContainer');
            if (lotSelector) lotSelector.style.display = 'block';
            showLotSelector(resolveResult.data);
            // Render empty state
            renderLotResults(resolveResult);
            // Auto-open the dropdown
            document.getElementById('lotSelectorDropdown').classList.add('show');
        }

    } catch (error) {
        document.getElementById('lotResultsContent').innerHTML = `<div class="error">查詢失敗: ${error.message}</div>`;
    } finally {
        document.getElementById('lotQueryBtn').disabled = false;
    }
}

// ============================================================
// LOT Selector Dropdown
// ============================================================

function showLotSelector(lots) {
    const container = document.getElementById('lotSelectorContainer');
    const dropdown = document.getElementById('lotSelectorDropdown');
    const display = document.getElementById('lotSelectorDisplay');
    const badge = document.getElementById('lotCountBadge');

    container.style.display = 'block';
    display.textContent = '選擇批次...';
    badge.textContent = lots.length + ' 筆';

    // Group lots by spec_name and sort within groups
    const groupedLots = {};
    lots.forEach((lot, idx) => {
        const spec = lot.spec_name || '未分類';
        if (!groupedLots[spec]) {
            groupedLots[spec] = [];
        }
        groupedLots[spec].push({ ...lot, originalIndex: idx });
    });

    // Sort specs alphabetically, sort lots within each group by lot_id
    const sortedSpecs = Object.keys(groupedLots).sort();
    sortedSpecs.forEach(spec => {
        groupedLots[spec].sort((a, b) => {
            const aId = a.lot_id || a.input_value || '';
            const bId = b.lot_id || b.input_value || '';
            return aId.localeCompare(bId);
        });
    });

    // Populate dropdown with grouped structure and checkboxes for multi-select
    let html = `
        <div style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
            <label style="cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 13px;">
                <input type="checkbox" id="lotSelectAll" onchange="toggleAllLotsInSelector(this.checked)">
                全選
            </label>
            <span style="font-size: 12px; color: #666;" id="lotSelectedCount">已選 0 筆</span>
        </div>
    `;

    sortedSpecs.forEach(spec => {
        html += `<div class="lot-group-header" style="padding: 6px 12px; background: #f0f0f0; font-size: 12px; font-weight: 600; color: #666;">${spec}</div>`;

        groupedLots[spec].forEach(lot => {
            const idx = lot.originalIndex;
            const isSelected = QueryToolState.timelineSelectedLots.has(idx);

            html += `
                <div class="lot-option ${isSelected ? 'selected' : ''}" data-index="${idx}" onclick="selectLotFromDropdown(${idx})">
                    <label class="lot-option-checkbox" onclick="event.stopPropagation();" style="display: flex; align-items: center; margin-right: 10px;">
                        <input type="checkbox" data-lot-index="${idx}" ${isSelected ? 'checked' : ''} onchange="event.stopPropagation(); toggleLotInSelector(${idx}, this.checked)">
                    </label>
                    <div class="lot-option-info" style="flex: 1;">
                        <div class="lot-option-id">${lot.lot_id || lot.input_value}</div>
                        <div class="lot-option-spec">${lot.work_order || ''}</div>
                    </div>
                </div>
            `;
        });
    });

    // Add confirm button at the bottom
    html += `
        <div style="padding: 10px 12px; border-top: 1px solid #e0e0e0; background: #f8f9fa; position: sticky; bottom: 0;">
            <button class="btn btn-primary btn-sm" style="width: 100%;" onclick="confirmLotSelection()">
                確定選擇
            </button>
        </div>
    `;

    dropdown.innerHTML = html;
    updateLotSelectorCount();
}

// Confirm selection and load data for all selected lots
async function confirmLotSelection() {
    const selectedIndices = Array.from(QueryToolState.timelineSelectedLots);

    if (selectedIndices.length === 0) {
        Toast.warning('請至少選擇一個批次');
        return;
    }

    // Close dropdowns
    document.getElementById('lotSelectorDropdown').classList.remove('show');
    const wcDropdown = document.getElementById('wcGroupDropdown');
    if (wcDropdown) wcDropdown.classList.remove('show');

    // Build workcenter_groups parameter
    const wcGroups = Array.from(QueryToolState.selectedWorkcenterGroups);
    const wcGroupsParam = wcGroups.length > 0 ? wcGroups.join(',') : null;

    // Update display
    const count = selectedIndices.length;
    document.getElementById('lotSelectorDisplay').textContent = `已選 ${count} 個批次`;

    // Hide single lot info bar, show loading
    document.getElementById('lotInfoBar').style.display = 'none';

    const panel = document.getElementById('lotResultsContent');
    const filterInfo = wcGroupsParam ? ` (篩選: ${wcGroups.length} 個站點群組)` : '';
    panel.innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <br>載入所選批次資料...${filterInfo}
        </div>
    `;

    // Clear cached histories when filter changes
    QueryToolState.lotHistories = {};

    // Load history for all selected lots WITH workcenter filter
    try {
        await Promise.all(selectedIndices.map(async (idx) => {
            const lot = QueryToolState.resolvedLots[idx];
            const params = { container_id: lot.container_id };
            if (wcGroupsParam) {
                params.workcenter_groups = wcGroupsParam;
            }

            const result = await MesApi.get('/api/query-tool/lot-history', { params });
            if (!result.error) {
                QueryToolState.lotHistories[lot.container_id] = result.data || [];
            }
        }));

        // Render combined view
        renderCombinedLotView(selectedIndices);

    } catch (error) {
        panel.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function toggleLotInSelector(index, checked) {
    if (checked) {
        QueryToolState.timelineSelectedLots.add(index);
    } else {
        QueryToolState.timelineSelectedLots.delete(index);
    }

    // Update visual style
    const option = document.querySelector(`.lot-option[data-index="${index}"]`);
    if (option) {
        option.classList.toggle('selected', checked);
    }

    updateLotSelectorCount();
    updateTimelineButton();
}

function toggleAllLotsInSelector(checked) {
    const checkboxes = document.querySelectorAll('#lotSelectorDropdown input[type="checkbox"][data-lot-index]');
    checkboxes.forEach(cb => {
        cb.checked = checked;
        const idx = parseInt(cb.dataset.lotIndex);
        if (checked) {
            QueryToolState.timelineSelectedLots.add(idx);
        } else {
            QueryToolState.timelineSelectedLots.delete(idx);
        }
    });
    updateLotSelectorCount();
    updateTimelineButton();
}

function updateLotSelectorCount() {
    const countEl = document.getElementById('lotSelectedCount');
    if (countEl) {
        countEl.textContent = `已選 ${QueryToolState.timelineSelectedLots.size} 筆`;
    }
}

function toggleLotSelector() {
    const dropdown = document.getElementById('lotSelectorDropdown');
    dropdown.classList.toggle('show');
}

function selectLotFromDropdown(index) {
    // Toggle checkbox selection
    const checkbox = document.querySelector(`#lotSelectorDropdown input[data-lot-index="${index}"]`);
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        toggleLotInSelector(index, checkbox.checked);
    }
}

function updateLotInfoBar(index) {
    const lot = QueryToolState.resolvedLots[index];
    if (!lot) return;

    const infoBar = document.getElementById('lotInfoBar');
    infoBar.style.display = 'flex';

    document.getElementById('infoLotId').textContent = lot.lot_id || lot.input_value || '-';
    document.getElementById('infoSpec').textContent = lot.spec_name || '-';
    document.getElementById('infoWorkOrder').textContent = lot.work_order || '-';

    // Step count will be updated after history loads
    document.getElementById('infoStepCount').textContent = '-';
}

function renderLotResults(resolveResult) {
    const lots = QueryToolState.resolvedLots;
    const notFound = resolveResult.not_found || [];

    let html = `
        <div class="result-header">
            <div class="result-info">
                共找到 ${lots.length} 個批次
                ${notFound.length > 0 ? `<span style="color: #dc3545;">（${notFound.length} 個未找到）</span>` : ''}
            </div>
            <div class="result-actions">
                <span style="font-size: 13px; color: #666;">請從上方選擇批次後點擊「確定選擇」</span>
            </div>
        </div>
    `;

    html += `<div class="empty-state" style="padding: 40px;"><p>請選擇要查看的批次</p></div>`;

    document.getElementById('lotResultsContent').innerHTML = html;
}

// Render combined view for multiple selected lots
function renderCombinedLotView(selectedIndices) {
    const lots = QueryToolState.resolvedLots;
    const panel = document.getElementById('lotResultsContent');

    // Collect all history data with LOT ID
    const allHistory = [];
    selectedIndices.forEach(idx => {
        const lot = lots[idx];
        const history = QueryToolState.lotHistories[lot.container_id] || [];
        history.forEach(step => {
            allHistory.push({
                ...step,
                LOT_ID: lot.lot_id || lot.input_value,
                LOT_INDEX: idx
            });
        });
    });

    // Sort by track-in time
    allHistory.sort((a, b) => {
        const timeA = a.TRACKINTIMESTAMP ? new Date(a.TRACKINTIMESTAMP).getTime() : 0;
        const timeB = b.TRACKINTIMESTAMP ? new Date(b.TRACKINTIMESTAMP).getTime() : 0;
        return timeA - timeB;
    });

    let html = `
        <div class="result-header">
            <div class="result-info">
                已選擇 ${selectedIndices.length} 個批次，共 ${allHistory.length} 筆生產紀錄
            </div>
            <div class="result-actions">
                <button class="btn btn-success btn-sm" onclick="exportCombinedResults()">匯出 CSV</button>
            </div>
        </div>
    `;

    // Timeline section (auto-displayed)
    html += `
        <div id="timelineContainer" style="margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div style="font-weight: 600; font-size: 16px;">
                    生產時間線
                    <span style="font-weight: normal; font-size: 13px; color: #666;">(${selectedIndices.length} 個批次)</span>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="document.getElementById('timelineContainer').style.display='none'">收起</button>
            </div>
            <div id="timelineContent"></div>
        </div>
    `;

    // Combined production history table with LOT ID column
    html += `
        <div style="font-weight: 600; margin-bottom: 15px; font-size: 16px;">生產歷程</div>
        <div class="table-container" style="max-height: 400px; overflow: auto;">
            <table style="min-width: 100%;">
                <thead>
                    <tr>
                        <th style="min-width: 140px; position: sticky; left: 0; background: #f8f9fa; z-index: 2;">LOT ID</th>
                        <th style="min-width: 100px;">站點</th>
                        <th style="min-width: 100px;">設備</th>
                        <th style="min-width: 120px;">規格</th>
                        <th style="min-width: 80px;">產品類型</th>
                        <th style="min-width: 80px;">BOP</th>
                        <th style="min-width: 100px;">Wafer Lot</th>
                        <th style="min-width: 150px;">上機時間</th>
                        <th style="min-width: 150px;">下機時間</th>
                        <th style="width: 70px;">入數</th>
                        <th style="width: 70px;">出數</th>
                        <th style="width: 80px; position: sticky; right: 0; background: #f8f9fa; box-shadow: -2px 0 4px rgba(0,0,0,0.1);">操作</th>
                    </tr>
                </thead>
                <tbody>
    `;

    allHistory.forEach((step, idx) => {
        html += `
            <tr class="lot-row" id="combined-row-${idx}">
                <td style="position: sticky; left: 0; background: white; z-index: 1; font-weight: 500; font-family: monospace; font-size: 12px;">${step.LOT_ID}</td>
                <td>${step.WORKCENTERNAME || ''}</td>
                <td>${step.EQUIPMENTNAME || ''}</td>
                <td title="${step.SPECNAME || ''}">${truncateText(step.SPECNAME, 15)}</td>
                <td>${step.PJ_TYPE || '-'}</td>
                <td>${step.PJ_BOP || '-'}</td>
                <td>${step.WAFER_LOT_ID || '-'}</td>
                <td>${formatDateTime(step.TRACKINTIMESTAMP)}</td>
                <td>${formatDateTime(step.TRACKOUTTIMESTAMP)}</td>
                <td>${step.TRACKINQTY || ''}</td>
                <td>${step.TRACKOUTQTY || ''}</td>
                <td style="position: sticky; right: 0; background: white; box-shadow: -2px 0 4px rgba(0,0,0,0.1);">
                    <button class="btn btn-secondary btn-sm" onclick="showAdjacentLots('${step.EQUIPMENTID}', '${step.EQUIPMENTNAME || step.EQUIPMENTID}', '${step.TRACKINTIMESTAMP}')" title="查詢前後批">
                        前後批
                    </button>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table></div>`;

    // Association tabs for combined data
    html += `
        <hr class="section-divider">
        <div style="font-weight: 600; margin-bottom: 15px;">關聯資料</div>
        <div class="assoc-tabs">
            <button class="assoc-tab active" onclick="loadCombinedAssociation('materials', this)">物料消耗</button>
            <button class="assoc-tab" onclick="loadCombinedAssociation('rejects', this)">不良紀錄</button>
            <button class="assoc-tab" onclick="loadCombinedAssociation('holds', this)">HOLD 紀錄</button>
            <button class="assoc-tab" onclick="loadCombinedAssociation('splits', this)">拆併批紀錄</button>
        </div>
        <div id="assocContent">
            <div class="loading"><div class="loading-spinner"></div></div>
        </div>
    `;

    panel.innerHTML = html;

    // Store selected indices for association queries
    QueryToolState.currentSelectedIndices = selectedIndices;

    // Set timeline selected lots for showTimeline() to work
    QueryToolState.timelineSelectedLots = new Set(selectedIndices);

    // Render timeline
    renderTimeline(selectedIndices);

    // Load default association
    loadCombinedAssociation('materials', document.querySelector('.assoc-tab.active'));
}

// Load combined association data for all selected lots
async function loadCombinedAssociation(type, tabElement) {
    // Update tab states
    document.querySelectorAll('.assoc-tab').forEach(t => t.classList.remove('active'));
    if (tabElement) tabElement.classList.add('active');

    const content = document.getElementById('assocContent');

    // Show custom loading message for splits (slow query)
    if (type === 'splits') {
        content.innerHTML = `
            <div class="loading" style="flex-direction: column; gap: 12px;">
                <div class="loading-spinner"></div>
                <div style="text-align: center; color: #666;">
                    <div style="font-weight: 500; margin-bottom: 4px;">查詢生產拆併批紀錄中...</div>
                    <div style="font-size: 12px;">此查詢可能需要 30-60 秒，請耐心等候</div>
                </div>
            </div>`;
    } else {
        content.innerHTML = `<div class="loading"><div class="loading-spinner"></div></div>`;
    }

    const selectedIndices = QueryToolState.currentSelectedIndices || [];
    const lots = QueryToolState.resolvedLots;

    try {
        // Special handling for 'splits' type - different data structure
        if (type === 'splits') {
            const combinedSplitsData = {
                production_history: [],
                serial_numbers: [],
                production_history_skipped: false,
                production_history_skip_reason: '',
                production_history_timeout: false,
                production_history_timeout_message: ''
            };

            await Promise.all(selectedIndices.map(async (idx) => {
                const lot = lots[idx];
                const cacheKey = `${lot.container_id}_${type}`;

                if (!QueryToolState.lotAssociations[cacheKey]) {
                    const result = await MesApi.get('/api/query-tool/lot-associations', {
                        params: { container_id: lot.container_id, type: type },
                        timeout: 120000  // 2 minute timeout for slow queries
                    });
                    // 'splits' returns {production_history, serial_numbers, ...} directly
                    // NOT wrapped in {data: ...}
                    QueryToolState.lotAssociations[cacheKey] = result || {};
                    // Debug: log the API response for splits
                    console.log('[DEBUG] Splits API response for', lot.container_id, ':', result);
                    console.log('[DEBUG] production_history count:', (result?.production_history || []).length);
                    console.log('[DEBUG] serial_numbers count:', (result?.serial_numbers || []).length);
                }

                const data = QueryToolState.lotAssociations[cacheKey];
                const lotId = lot.lot_id || lot.input_value;

                // Capture skip info from first response
                if (data.production_history_skipped && !combinedSplitsData.production_history_skipped) {
                    combinedSplitsData.production_history_skipped = true;
                    combinedSplitsData.production_history_skip_reason = data.production_history_skip_reason || '';
                }

                // Capture timeout info
                if (data.production_history_timeout && !combinedSplitsData.production_history_timeout) {
                    combinedSplitsData.production_history_timeout = true;
                    combinedSplitsData.production_history_timeout_message = data.production_history_timeout_message || '查詢逾時';
                }

                // Merge production_history with LOT_ID
                (data.production_history || []).forEach(record => {
                    combinedSplitsData.production_history.push({
                        ...record,
                        LOT_ID: lotId
                    });
                });

                // Merge serial_numbers with LOT_ID
                (data.serial_numbers || []).forEach(snGroup => {
                    // Check if this serial number already exists
                    const existingSn = combinedSplitsData.serial_numbers.find(
                        s => s.serial_number === snGroup.serial_number
                    );
                    if (existingSn) {
                        // Merge lots into existing serial number
                        snGroup.lots.forEach(lot => {
                            if (!existingSn.lots.some(l => l.container_id === lot.container_id)) {
                                existingSn.lots.push(lot);
                            }
                        });
                        existingSn.total_good_die = existingSn.lots.reduce(
                            (sum, l) => sum + (l.good_die_qty || 0), 0
                        );
                    } else {
                        combinedSplitsData.serial_numbers.push({
                            ...snGroup,
                            LOT_ID: lotId
                        });
                    }
                });
            }));

            // Sort production history by date
            combinedSplitsData.production_history.sort((a, b) => {
                const dateA = a.txn_date ? new Date(a.txn_date).getTime() : 0;
                const dateB = b.txn_date ? new Date(b.txn_date).getTime() : 0;
                return dateA - dateB;
            });

            // Save to state for export functionality
            QueryToolState.combinedSplitsData = combinedSplitsData;

            renderCombinedAssociation(type, combinedSplitsData);
            return;
        }

        // Standard handling for other types (materials, rejects, holds)
        const allData = [];

        await Promise.all(selectedIndices.map(async (idx) => {
            const lot = lots[idx];
            const cacheKey = `${lot.container_id}_${type}`;

            if (!QueryToolState.lotAssociations[cacheKey]) {
                const result = await MesApi.get('/api/query-tool/lot-associations', {
                    params: { container_id: lot.container_id, type: type }
                });
                QueryToolState.lotAssociations[cacheKey] = result.data || [];
            }

            const data = QueryToolState.lotAssociations[cacheKey];
            data.forEach(row => {
                allData.push({
                    ...row,
                    LOT_ID: lot.lot_id || lot.input_value
                });
            });
        }));

        renderCombinedAssociation(type, allData);

    } catch (error) {
        content.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function renderCombinedAssociation(type, data) {
    const content = document.getElementById('assocContent');

    // Special handling for 'splits' type (different data structure)
    if (type === 'splits') {
        renderCombinedSplitsAssociation(data);
        return;
    }

    // Check for empty data (array types)
    if (!data || data.length === 0) {
        content.innerHTML = `<div class="empty-state" style="padding: 30px;"><p>無${getAssocLabel(type)}資料</p></div>`;
        return;
    }

    // Define columns with LOT_ID first
    const columnDefs = {
        'materials': ['LOT_ID', 'MATERIALPARTNAME', 'MATERIALLOTNAME', 'QTYCONSUMED', 'WORKCENTERNAME', 'EQUIPMENTNAME', 'TXNDATE'],
        'rejects': ['LOT_ID', 'REJECTCATEGORYNAME', 'LOSSREASONNAME', 'REJECTQTY', 'WORKCENTERNAME', 'EQUIPMENTNAME', 'TXNDATE'],
        'holds': ['LOT_ID', 'WORKCENTERNAME', 'HOLDREASONNAME', 'HOLDTXNDATE', 'HOLD_STATUS', 'HOLD_HOURS', 'HOLDEMP', 'RELEASETXNDATE'],
    };

    const colLabels = {
        'LOT_ID': 'LOT ID',
        'MATERIALPARTNAME': '物料名稱',
        'MATERIALLOTNAME': '物料批號',
        'QTYCONSUMED': '消耗數量',
        'WORKCENTERNAME': '站點',
        'EQUIPMENTNAME': '設備',
        'TXNDATE': '時間',
        'REJECTCATEGORYNAME': '不良分類',
        'LOSSREASONNAME': '損失原因',
        'REJECTQTY': '不良數量',
        'HOLDREASONNAME': 'HOLD 原因',
        'HOLDTXNDATE': 'HOLD 時間',
        'HOLD_STATUS': '狀態',
        'HOLD_HOURS': 'HOLD 時數',
        'HOLDEMP': 'HOLD 人員',
        'RELEASETXNDATE': 'RELEASE 時間',
    };

    const cols = columnDefs[type] || ['LOT_ID', ...Object.keys(data[0]).filter(k => k !== 'LOT_ID')];

    let html = `<div class="table-container" style="max-height: 350px;"><table><thead><tr>`;
    cols.forEach(col => {
        const isLotId = col === 'LOT_ID';
        const style = isLotId ? 'position: sticky; left: 0; background: #f8f9fa; z-index: 2;' : '';
        html += `<th style="${style}">${colLabels[col] || col}</th>`;
    });
    html += `</tr></thead><tbody>`;

    data.forEach(row => {
        html += `<tr>`;
        cols.forEach(col => {
            let value = row[col];
            const isLotId = col === 'LOT_ID';
            const style = isLotId ? 'position: sticky; left: 0; background: white; z-index: 1; font-weight: 500; font-family: monospace; font-size: 12px;' : '';

            if (col.includes('DATE') || col.includes('TIMESTAMP')) {
                value = formatDateTime(value);
            }
            if (col === 'HOLD_STATUS') {
                value = value === 'HOLD'
                    ? `<span class="badge badge-warning">HOLD 中</span>`
                    : `<span class="badge badge-success">已解除</span>`;
            }
            html += `<td style="${style}">${value !== null && value !== undefined ? value : ''}</td>`;
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>`;
    content.innerHTML = html;
}

function renderCombinedSplitsAssociation(data) {
    const content = document.getElementById('assocContent');

    // New data structure has: production_history, serial_numbers, skip/timeout info
    const productionHistory = data.production_history || [];
    const serialNumbers = data.serial_numbers || [];
    const productionHistorySkipped = data.production_history_skipped || false;
    const skipReason = data.production_history_skip_reason || '';
    const productionHistoryTimeout = data.production_history_timeout || false;
    const timeoutMessage = data.production_history_timeout_message || '';
    const hasProductionHistory = productionHistory.length > 0;
    const hasSerialNumbers = serialNumbers.length > 0;

    if (!hasProductionHistory && !hasSerialNumbers && !productionHistorySkipped && !productionHistoryTimeout) {
        content.innerHTML = '<div class="empty-state" style="padding: 30px;"><p>無拆併批紀錄</p></div>';
        return;
    }

    let html = '';

    // Show notice if production history query was skipped
    if (productionHistorySkipped && skipReason) {
        html += `
            <div style="margin-bottom: 16px; padding: 12px 16px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; font-size: 13px; color: #856404;">
                <strong>注意：</strong>${skipReason}
            </div>
        `;
    }

    // Show warning if production history query timed out
    if (productionHistoryTimeout) {
        html += `
            <div style="margin-bottom: 16px; padding: 12px 16px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; font-size: 13px; color: #721c24;">
                <strong>⚠ 查詢逾時：</strong>${timeoutMessage || '生產拆併批歷史查詢超時。此表格（DW_MES_HM_LOTMOVEOUT）目前無索引，查詢需較長時間。僅顯示 TMTT 成品流水號對應資料。'}
            </div>
        `;
    }

    // 1. Production Split/Merge History (生產過程拆併批)
    if (hasProductionHistory) {
        html += `
            <div style="margin-bottom: 24px;">
                <div style="font-weight: 600; font-size: 15px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span>生產過程拆併批紀錄</span>
                        <span style="font-size: 12px; color: #666; font-weight: normal;">(${productionHistory.length} 筆)</span>
                    </div>
                    <button class="btn btn-success btn-sm" onclick="exportProductionHistory('combined')">匯出 CSV</button>
                </div>
                <div class="table-container" style="max-height: 300px; overflow: auto;">
                    <table style="min-width: 100%; font-size: 13px;">
                        <thead>
                            <tr>
                                <th style="min-width: 70px;">操作</th>
                                <th style="min-width: 120px;">來源批次</th>
                                <th style="min-width: 120px;">目標批次</th>
                                <th style="min-width: 60px;">數量</th>
                                <th style="min-width: 140px;">時間</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        productionHistory.forEach(record => {
            const opBadgeClass = record.operation_type === 'SplitLot' ? 'badge-info' : 'badge-warning';
            const isCurrentSource = record.is_current_lot_source;
            const isCurrentTarget = record.is_current_lot_target;
            const sourceStyle = isCurrentSource ? 'font-weight: 600; color: #4e54c8;' : '';
            const targetStyle = isCurrentTarget ? 'font-weight: 600; color: #4e54c8;' : '';

            html += `
                <tr>
                    <td><span class="badge ${opBadgeClass}">${record.operation_type_display}</span></td>
                    <td style="${sourceStyle}">${record.source_lot || '-'}</td>
                    <td style="${targetStyle}">${record.target_lot || '-'}</td>
                    <td>${record.target_qty || '-'}</td>
                    <td>${formatDateTime(record.txn_date)}</td>
                </tr>
            `;
        });

        html += `</tbody></table></div></div>`;
    }

    // 2. TMTT Serial Number Mapping (成品流水號對應)
    if (hasSerialNumbers) {
        html += `
            <div style="margin-bottom: 12px;">
                <div style="font-weight: 600; font-size: 15px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span>成品流水號對應</span>
                        <span style="font-size: 12px; color: #666; font-weight: normal;">(${serialNumbers.length} 個流水號)</span>
                    </div>
                    <button class="btn btn-success btn-sm" onclick="exportSerialNumbers('combined')">匯出 CSV</button>
                </div>
        `;

        serialNumbers.forEach(snGroup => {
            const sn = snGroup.serial_number || 'Unknown';
            const lots = snGroup.lots || [];
            const totalDie = snGroup.total_good_die || 0;

            html += `
                <div style="margin-bottom: 12px; padding: 12px; border: 1px solid #dee2e6; border-radius: 6px; background: #fafafa;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 600; font-size: 14px;">流水號: ${sn}</span>
                        <span style="font-size: 12px; color: #666;">總 Good Die: ${totalDie}</span>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            `;

            lots.forEach(lot => {
                const isCurrentLot = lot.is_current;
                const lotStyle = isCurrentLot
                    ? 'background: #e8f4e8; border: 1px solid #4caf50;'
                    : 'background: white; border: 1px solid #ddd;';

                html += `
                    <div style="padding: 6px 10px; border-radius: 4px; font-size: 12px; ${lotStyle}">
                        <div style="font-weight: 500;">${lot.lot_id || '-'}</div>
                        <div style="color: #666; font-size: 11px;">
                            ${lot.combine_ratio_pct} · ${lot.good_die_qty || 0} die
                        </div>
                    </div>
                `;
            });

            html += `</div></div>`;
        });

        html += `</div>`;
    }

    content.innerHTML = html;
}

async function selectLot(index) {
    QueryToolState.selectedLotIndex = index;

    // Update LOT selector dropdown display
    const lot = QueryToolState.resolvedLots[index];
    const display = document.getElementById('lotSelectorDisplay');
    if (display && lot) {
        display.textContent = lot.lot_id || lot.input_value;
    }

    // Update dropdown active state
    document.querySelectorAll('.lot-option').forEach((el, idx) => {
        el.classList.toggle('active', idx === index);
    });

    // Update info bar
    updateLotInfoBar(index);

    // Load history if not cached
    loadLotHistory(index);
}

async function loadLotHistory(index) {
    const lot = QueryToolState.resolvedLots[index];
    const containerId = lot.container_id;

    const panel = document.getElementById('lotDetailPanel');
    panel.innerHTML = `<div class="loading"><div class="loading-spinner"></div><br>載入生產歷程...</div>`;

    // Check cache
    if (QueryToolState.lotHistories[containerId]) {
        renderLotDetail(index);
        // Update step count in info bar
        const stepCount = QueryToolState.lotHistories[containerId].length;
        document.getElementById('infoStepCount').textContent = stepCount + ' 站';
        return;
    }

    try {
        const result = await MesApi.get('/api/query-tool/lot-history', {
            params: { container_id: containerId }
        });

        if (result.error) {
            panel.innerHTML = `<div class="error">${result.error}</div>`;
            return;
        }

        QueryToolState.lotHistories[containerId] = result.data || [];

        // Update step count in info bar
        const stepCount = (result.data || []).length;
        document.getElementById('infoStepCount').textContent = stepCount + ' 站';

        renderLotDetail(index);

    } catch (error) {
        panel.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function renderLotDetail(index) {
    const lot = QueryToolState.resolvedLots[index];
    const containerId = lot.container_id;
    const lotId = lot.lot_id || lot.input_value;  // LOT ID for display
    const history = QueryToolState.lotHistories[containerId] || [];

    const panel = document.getElementById('lotDetailPanel');

    let html = '';

    if (history.length === 0) {
        html += `<div class="empty-state"><p>無生產歷程資料</p></div>`;
    } else {
        // Production history table (full width)
        html += `
            <div style="font-weight: 600; margin-bottom: 15px; font-size: 16px;">生產歷程</div>
            <div class="table-container" style="max-height: 350px; overflow: auto;">
                <table style="min-width: 100%;">
                    <thead>
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th style="min-width: 100px;">站點</th>
                            <th style="min-width: 100px;">設備</th>
                            <th style="min-width: 120px;">規格</th>
                            <th style="min-width: 80px;">產品類型</th>
                            <th style="min-width: 80px;">BOP</th>
                            <th style="min-width: 100px;">Wafer Lot</th>
                            <th style="min-width: 150px;">上機時間</th>
                            <th style="min-width: 150px;">下機時間</th>
                            <th style="width: 70px;">入數</th>
                            <th style="width: 70px;">出數</th>
                            <th style="width: 80px; position: sticky; right: 0; background: #f8f9fa; box-shadow: -2px 0 4px rgba(0,0,0,0.1);">操作</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        history.forEach((step, idx) => {
            html += `
                <tr class="lot-row" id="history-row-${idx}">
                    <td>${idx + 1}</td>
                    <td>${step.WORKCENTERNAME || ''}</td>
                    <td>${step.EQUIPMENTNAME || ''}</td>
                    <td title="${step.SPECNAME || ''}">${truncateText(step.SPECNAME, 12)}</td>
                    <td>${step.PJ_TYPE || '-'}</td>
                    <td>${step.PJ_BOP || '-'}</td>
                    <td>${step.WAFER_LOT_ID || '-'}</td>
                    <td>${formatDateTime(step.TRACKINTIMESTAMP)}</td>
                    <td>${formatDateTime(step.TRACKOUTTIMESTAMP)}</td>
                    <td>${step.TRACKINQTY || ''}</td>
                    <td>${step.TRACKOUTQTY || ''}</td>
                    <td style="position: sticky; right: 0; background: white; box-shadow: -2px 0 4px rgba(0,0,0,0.1);">
                        <button class="btn btn-secondary btn-sm" onclick="showAdjacentLots('${step.EQUIPMENTID}', '${step.EQUIPMENTNAME || step.EQUIPMENTID}', '${step.TRACKINTIMESTAMP}')" title="查詢前後批">
                            前後批
                        </button>
                    </td>
                </tr>
            `;
        });

        html += `</tbody></table></div>`;
    }

    // Association tabs
    html += `
        <hr class="section-divider">
        <div style="font-weight: 600; margin-bottom: 15px;">關聯資料</div>
        <div class="assoc-tabs">
            <button class="assoc-tab active" onclick="loadAssociation('${containerId}', 'materials', this)">物料消耗</button>
            <button class="assoc-tab" onclick="loadAssociation('${containerId}', 'rejects', this)">不良紀錄</button>
            <button class="assoc-tab" onclick="loadAssociation('${containerId}', 'holds', this)">HOLD 紀錄</button>
            <button class="assoc-tab" onclick="loadAssociation('${containerId}', 'splits', this)">拆併批紀錄</button>
        </div>
        <div id="assocContent">
            <div class="loading"><div class="loading-spinner"></div></div>
        </div>
    `;

    panel.innerHTML = html;

    // Load default association (materials)
    loadAssociation(containerId, 'materials', document.querySelector('.assoc-tab.active'));
}

async function loadAssociation(containerId, type, tabElement) {
    // Update tab states
    document.querySelectorAll('.assoc-tab').forEach(t => t.classList.remove('active'));
    if (tabElement) tabElement.classList.add('active');

    // Save current container ID for export functions
    QueryToolState.currentContainerId = containerId;

    const content = document.getElementById('assocContent');

    // Show custom loading message for splits (slow query)
    if (type === 'splits') {
        content.innerHTML = `
            <div class="loading" style="flex-direction: column; gap: 12px;">
                <div class="loading-spinner"></div>
                <div style="text-align: center; color: #666;">
                    <div style="font-weight: 500; margin-bottom: 4px;">查詢生產拆併批紀錄中...</div>
                    <div style="font-size: 12px;">此查詢可能需要 30-60 秒，請耐心等候</div>
                </div>
            </div>`;
    } else {
        content.innerHTML = `<div class="loading"><div class="loading-spinner"></div></div>`;
    }

    // Check cache
    const cacheKey = `${containerId}_${type}`;
    if (QueryToolState.lotAssociations[cacheKey]) {
        renderAssociation(type, QueryToolState.lotAssociations[cacheKey]);
        return;
    }

    try {
        const result = await MesApi.get('/api/query-tool/lot-associations', {
            params: { container_id: containerId, type: type },
            timeout: type === 'splits' ? 120000 : 60000  // 2 minutes for splits, 1 minute for others
        });

        if (result.error) {
            content.innerHTML = `<div class="error">${result.error}</div>`;
            return;
        }

        // 'splits' returns {production_history, serial_numbers, ...} directly
        // Other types return {data: [...], ...}
        if (type === 'splits') {
            QueryToolState.lotAssociations[cacheKey] = result || {};
            renderAssociation(type, result || {});
        } else {
            QueryToolState.lotAssociations[cacheKey] = result.data || [];
            renderAssociation(type, result.data || []);
        }

    } catch (error) {
        content.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function renderAssociation(type, data) {
    const content = document.getElementById('assocContent');

    // Special handling for 'splits' type (object with production_history and serial_numbers)
    if (type === 'splits') {
        renderSplitsAssociation(data);
        return;
    }

    // Check empty data for array-based types
    if (!data || data.length === 0) {
        content.innerHTML = `<div class="empty-state" style="padding: 30px;"><p>無${getAssocLabel(type)}資料</p></div>`;
        return;
    }

    let html = `<div class="table-container" style="max-height: 300px;"><table><thead><tr>`;

    // Define columns based on type
    const columns = {
        'materials': ['MATERIALPARTNAME', 'MATERIALLOTNAME', 'QTYCONSUMED', 'WORKCENTERNAME', 'EQUIPMENTNAME', 'TXNDATE'],
        'rejects': ['REJECTCATEGORYNAME', 'LOSSREASONNAME', 'REJECTQTY', 'WORKCENTERNAME', 'EQUIPMENTNAME', 'TXNDATE'],
        'holds': ['WORKCENTERNAME', 'HOLDREASONNAME', 'HOLDTXNDATE', 'HOLD_STATUS', 'HOLD_HOURS', 'HOLDEMP', 'RELEASETXNDATE'],
    };

    const colLabels = {
        'MATERIALPARTNAME': '物料名稱',
        'MATERIALLOTNAME': '物料批號',
        'QTYCONSUMED': '消耗數量',
        'WORKCENTERNAME': '站點',
        'EQUIPMENTNAME': '設備',
        'TXNDATE': '時間',
        'REJECTCATEGORYNAME': '不良分類',
        'LOSSREASONNAME': '損失原因',
        'REJECTQTY': '不良數量',
        'HOLDREASONNAME': 'HOLD 原因',
        'HOLDTXNDATE': 'HOLD 時間',
        'HOLD_STATUS': '狀態',
        'HOLD_HOURS': 'HOLD 時數',
        'HOLDEMP': 'HOLD 人員',
        'RELEASETXNDATE': 'RELEASE 時間',
    };

    const cols = columns[type] || Object.keys(data[0]);
    cols.forEach(col => {
        html += `<th>${colLabels[col] || col}</th>`;
    });
    html += `</tr></thead><tbody>`;

    data.forEach(row => {
        html += `<tr>`;
        cols.forEach(col => {
            let value = row[col];
            if (col.includes('DATE') || col.includes('TIMESTAMP')) {
                value = formatDateTime(value);
            }
            if (col === 'HOLD_STATUS') {
                value = value === 'HOLD'
                    ? `<span class="badge badge-warning">HOLD 中</span>`
                    : `<span class="badge badge-success">已解除</span>`;
            }
            html += `<td>${value !== null && value !== undefined ? value : ''}</td>`;
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>`;
    content.innerHTML = html;
}

function renderSplitsAssociation(data) {
    const content = document.getElementById('assocContent');

    // Handle new format: {production_history: [], serial_numbers: [], skip/timeout info, ...}
    const productionHistory = data.production_history || [];
    const serialNumbers = data.serial_numbers || [];
    const productionHistorySkipped = data.production_history_skipped || false;
    const skipReason = data.production_history_skip_reason || '';
    const productionHistoryTimeout = data.production_history_timeout || false;
    const timeoutMessage = data.production_history_timeout_message || '';
    const hasProductionHistory = productionHistory.length > 0;
    const hasSerialNumbers = serialNumbers.length > 0;

    if (!hasProductionHistory && !hasSerialNumbers && !productionHistoryTimeout) {
        let emptyHtml = '';
        if (productionHistorySkipped && skipReason) {
            emptyHtml += `
                <div style="margin-bottom: 16px; padding: 12px 16px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; font-size: 13px; color: #856404;">
                    <strong>注意：</strong>${skipReason}
                </div>
            `;
        }
        emptyHtml += '<div class="text-center text-muted py-4">無拆併批紀錄</div>';
        content.innerHTML = emptyHtml;
        return;
    }

    let html = '';

    // Show notice if production history query was skipped
    if (productionHistorySkipped && skipReason) {
        html += `
            <div style="margin-bottom: 16px; padding: 12px 16px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; font-size: 13px; color: #856404;">
                <strong>注意：</strong>${skipReason}
            </div>
        `;
    }

    // Show warning if production history query timed out
    if (productionHistoryTimeout) {
        html += `
            <div style="margin-bottom: 16px; padding: 12px 16px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; font-size: 13px; color: #721c24;">
                <strong>⚠ 查詢逾時：</strong>${timeoutMessage || '生產拆併批歷史查詢超時。此表格（DW_MES_HM_LOTMOVEOUT）目前無索引，查詢需較長時間。僅顯示 TMTT 成品流水號對應資料。'}
            </div>
        `;
    }

    // Production history section (if any)
    if (hasProductionHistory) {
        html += `
            <div style="margin-bottom: 24px;">
                <div style="font-weight: 600; font-size: 15px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; justify-content: space-between;">
                    <div>
                        生產過程拆併批紀錄 <span style="font-size: 12px; color: #666; font-weight: normal;">(${productionHistory.length} 筆)</span>
                    </div>
                    <button class="btn btn-success btn-sm" onclick="exportProductionHistory('single')">匯出 CSV</button>
                </div>
                <div class="table-container" style="max-height: 250px; overflow: auto;">
                    <table style="min-width: 100%; font-size: 13px;">
                        <thead>
                            <tr>
                                <th style="min-width: 70px;">操作</th>
                                <th style="min-width: 100px;">來源批次</th>
                                <th style="min-width: 100px;">目標批次</th>
                                <th style="min-width: 60px;">數量</th>
                                <th style="min-width: 130px;">時間</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        productionHistory.forEach(record => {
            const opBadgeClass = record.operation_type === 'SplitLot' ? 'badge-info' : 'badge-warning';
            html += `
                <tr>
                    <td><span class="badge ${opBadgeClass}">${record.operation_type_display}</span></td>
                    <td>${record.source_lot || '-'}</td>
                    <td>${record.target_lot || '-'}</td>
                    <td>${record.target_qty || '-'}</td>
                    <td>${formatDateTime(record.txn_date)}</td>
                </tr>
            `;
        });

        html += `</tbody></table></div></div>`;
    }

    // Serial numbers section
    if (!hasSerialNumbers) {
        if (hasProductionHistory) {
            html += '<div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 6px; text-align: center; color: #666;">此 LOT 尚未產出成品流水號</div>';
        }
        content.innerHTML = html;
        return;
    }

    html += `
        <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
            <div style="color: #666; font-size: 13px;">
                此 LOT 參與產出 <strong>${serialNumbers.length}</strong> 個成品流水號，以下顯示各成品的來源批次組成
            </div>
            <button class="btn btn-success btn-sm" onclick="exportSerialNumbers('single')">匯出 CSV</button>
        </div>
    `;

    serialNumbers.forEach((item, idx) => {
        const lots = item.lots || [];
        const totalGoodDie = item.total_good_die || 0;
        const isCombined = lots.length > 1;

        html += `
            <div style="margin-bottom: 20px; border: 1px solid #dee2e6; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600; font-size: 15px;">
                        成品流水號: ${item.serial_number || '-'}
                    </span>
                    <span style="font-size: 12px; opacity: 0.9;">
                        ${isCombined ? `${lots.length} 批合併` : '單批產出'} |
                        良品總數: ${totalGoodDie.toLocaleString()}
                    </span>
                </div>
                <div style="padding: 0; overflow-x: auto;">
                    <table style="min-width: 100%; margin: 0; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8f9fa;">
                                <th style="width: 50px; padding: 10px 12px; text-align: center; border-bottom: 2px solid #dee2e6;">序</th>
                                <th style="padding: 10px 12px; text-align: left; border-bottom: 2px solid #dee2e6; min-width: 180px;">LOT ID</th>
                                <th style="padding: 10px 12px; text-align: left; border-bottom: 2px solid #dee2e6; min-width: 120px;">工單</th>
                                <th style="padding: 10px 12px; text-align: right; border-bottom: 2px solid #dee2e6; width: 100px;">貢獻比例</th>
                                <th style="padding: 10px 12px; text-align: right; border-bottom: 2px solid #dee2e6; width: 120px;">良品數</th>
                                <th style="padding: 10px 12px; text-align: left; border-bottom: 2px solid #dee2e6; min-width: 160px;">開始時間</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        lots.forEach((lot, lotIdx) => {
            const isCurrent = lot.is_current;
            const rowStyle = isCurrent
                ? 'background: #fff3cd; border-left: 4px solid #ffc107;'
                : 'border-left: 4px solid transparent;';
            const ratioValue = lot.combine_ratio || 0;
            const ratioBarWidth = Math.min(ratioValue * 100, 100);

            html += `
                <tr style="${rowStyle}">
                    <td style="padding: 10px 12px; text-align: center; border-bottom: 1px solid #eee;">${lotIdx + 1}</td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #eee;">
                        <div style="font-weight: 500;">${lot.lot_id || '-'}</div>
                        ${isCurrent ? '<span style="display: inline-block; margin-top: 2px; padding: 2px 6px; background: #856404; color: white; font-size: 10px; border-radius: 3px;">當前查詢批次</span>' : ''}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #eee; color: #666;">${lot.work_order || '-'}</td>
                    <td style="padding: 10px 12px; text-align: right; border-bottom: 1px solid #eee;">
                        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 8px;">
                            <div style="width: 60px; height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
                                <div style="width: ${ratioBarWidth}%; height: 100%; background: ${ratioValue >= 1 ? '#28a745' : '#17a2b8'}; border-radius: 3px;"></div>
                            </div>
                            <span style="font-weight: 500; min-width: 45px;">${lot.combine_ratio_pct || '-'}</span>
                        </div>
                    </td>
                    <td style="padding: 10px 12px; text-align: right; border-bottom: 1px solid #eee; font-family: monospace;">
                        ${lot.good_die_qty ? lot.good_die_qty.toLocaleString() : '-'}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #eee; color: #666; font-size: 13px;">
                        ${formatDateTime(lot.original_start_date)}
                    </td>
                </tr>
            `;
        });

        html += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    });

    content.innerHTML = html;
}

function getAssocLabel(type) {
    const labels = {
        'materials': '物料消耗',
        'rejects': '不良紀錄',
        'holds': 'HOLD 紀錄',
        'splits': '拆併批紀錄',
        'jobs': 'JOB 紀錄'
    };
    return labels[type] || type;
}

// ============================================================
// Timeline Functions
// ============================================================

function toggleLotForTimeline(index, checked) {
    // Delegate to the selector function
    toggleLotInSelector(index, checked);
}

function toggleAllLotsForTimeline(checked) {
    // This function is now handled by toggleAllLotsInSelector
    toggleAllLotsInSelector(checked);
}

function updateTimelineButton() {
    const btn = document.getElementById('timelineBtn');
    const count = QueryToolState.timelineSelectedLots.size;
    if (btn) {
        btn.disabled = count === 0;
        btn.textContent = count > 0 ? `顯示時間線 (${count})` : '顯示時間線';
    }
}

async function showTimeline() {
    const selectedIndices = Array.from(QueryToolState.timelineSelectedLots);
    if (selectedIndices.length === 0) {
        Toast.warning('請先勾選要顯示時間線的批次');
        return;
    }

    const container = document.getElementById('timelineContainer');
    const content = document.getElementById('timelineContent');
    const countSpan = document.getElementById('timelineCount');

    container.style.display = 'block';
    countSpan.textContent = `(${selectedIndices.length} 個批次)`;
    content.innerHTML = '<div class="loading"><div class="loading-spinner"></div><br>載入時間線資料...</div>';

    // Scroll to timeline
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Load history for all selected lots
    const lotsToLoad = [];
    for (const idx of selectedIndices) {
        const lot = QueryToolState.resolvedLots[idx];
        if (!QueryToolState.lotHistories[lot.container_id]) {
            lotsToLoad.push({ idx, lot });
        }
    }

    // Load missing histories
    try {
        await Promise.all(lotsToLoad.map(async ({ idx, lot }) => {
            const result = await MesApi.get('/api/query-tool/lot-history', {
                params: { container_id: lot.container_id }
            });
            if (!result.error) {
                QueryToolState.lotHistories[lot.container_id] = result.data || [];
            }
        }));

        renderTimeline(selectedIndices);
    } catch (error) {
        content.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function hideTimeline() {
    document.getElementById('timelineContainer').style.display = 'none';
}

function renderTimeline(selectedIndices) {
    const content = document.getElementById('timelineContent');

    // Collect all history data and find time bounds
    const lotsData = [];
    let minTime = Infinity;
    let maxTime = -Infinity;

    // Station color map
    const stationColors = {};
    const colorPalette = [
        '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
        '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
        '#86bcb6', '#8cd17d', '#499894', '#d37295', '#b6992d'
    ];
    let colorIndex = 0;

    for (const idx of selectedIndices) {
        const lot = QueryToolState.resolvedLots[idx];
        const history = QueryToolState.lotHistories[lot.container_id] || [];

        const steps = history.map((step, stepIdx) => {
            // Parse track-in time with better handling
            const trackInRaw = step.TRACKINTIMESTAMP;
            let trackIn = 0;
            if (trackInRaw) {
                // Try parsing - handle both ISO and Oracle formats
                const parsed = new Date(trackInRaw);
                if (!isNaN(parsed.getTime())) {
                    trackIn = parsed.getTime();
                }
            }

            // Check if TRACKOUTTIMESTAMP is a valid value (not null, not empty string, not "None")
            const trackOutRaw = step.TRACKOUTTIMESTAMP;
            const hasValidTrackOut = trackOutRaw &&
                trackOutRaw !== '' &&
                trackOutRaw !== 'None' &&
                trackOutRaw !== 'null' &&
                !isNaN(new Date(trackOutRaw).getTime());

            // For ongoing steps (no track-out), use track-in + 1 hour as placeholder
            // This prevents using Date.now() which can skew the timeline range
            const trackOut = hasValidTrackOut
                ? new Date(trackOutRaw).getTime()
                : (trackIn > 0 ? trackIn + 3600000 : 0);  // trackIn + 1 hour for ongoing
            const isOngoing = !hasValidTrackOut;

            // Only process steps with valid trackIn (skip pre-scheduled steps)
            if (trackIn > 0) {
                if (trackIn < minTime) minTime = trackIn;
                // For maxTime, use trackOut if valid, otherwise use trackIn
                const effectiveMax = hasValidTrackOut ? trackOut : trackIn;
                if (effectiveMax > maxTime) maxTime = effectiveMax;
            }

            // Assign color to station
            const station = step.WORKCENTERNAME || 'Unknown';
            if (!stationColors[station]) {
                stationColors[station] = colorPalette[colorIndex % colorPalette.length];
                colorIndex++;
            }

            return {
                station,
                equipment: step.EQUIPMENTNAME || '',
                spec: step.SPECNAME || '',
                trackIn,
                trackOut,
                color: stationColors[station],
                isOngoing
            };
        });

        lotsData.push({
            lotId: lot.lot_id || lot.input_value,
            containerId: lot.container_id,
            steps
        });
    }

    if (lotsData.length === 0 || minTime === Infinity) {
        content.innerHTML = '<div class="empty-state"><p>無生產歷程資料可顯示</p></div>';
        return;
    }

    // Add padding to time range
    const timeRange = maxTime - minTime;
    const padding = timeRange * 0.02;
    minTime -= padding;
    maxTime += padding;

    // Store timeline data for filtering and popup
    const allStations = Object.keys(stationColors);
    window._timelineData = {
        lotsData,
        minTime,
        maxTime,
        stationColors,
        allStations,
        selectedStations: new Set(allStations),  // All selected by default
        pixelsPerHour: 50
    };

    // Render compact preview with click to open popup
    let html = `
        <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
            <div style="font-size: 12px; color: #666; margin-bottom: 8px;">站點篩選 (點擊切換顯示)</div>
            <div id="stationFilterLegend" style="display: flex; flex-wrap: wrap; gap: 6px;">
                ${allStations.map(station => `
                    <span class="station-filter-item active" data-station="${station}" onclick="toggleStationFilter('${station}')"
                          style="background: ${stationColors[station]}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; transition: opacity 0.2s;">
                        ${station}
                    </span>
                `).join('')}
            </div>
            <div style="margin-top: 10px; display: flex; gap: 8px;">
                <button class="btn btn-secondary btn-sm" onclick="selectAllStations()">全選</button>
                <button class="btn btn-secondary btn-sm" onclick="deselectAllStations()">全不選</button>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-weight: 600;">時間線預覽</div>
            <span style="font-size: 12px; color: #888;">點擊開啟完整視窗</span>
        </div>

        <div id="timelinePreview" onclick="openTimelinePopup()" style="cursor: pointer; padding: 15px; background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; transition: box-shadow 0.2s;" onmouseover="this.style.boxShadow='0 4px 12px rgba(0,0,0,0.1)'" onmouseout="this.style.boxShadow='none'">
            ${renderTimelinePreview(lotsData, minTime, maxTime, stationColors)}
        </div>

        <div style="text-align: center; margin-top: 10px; font-size: 12px; color: #888;">
            支援縮放和橫向捲動
        </div>
    `;

    content.innerHTML = html;
}

function renderTimelinePreview(lotsData, minTime, maxTime, stationColors) {
    const MS_PER_HOUR = 3600000;
    const PREVIEW_WIDTH = 600;  // Fixed preview width
    const timeRange = maxTime - minTime;
    const selectedStations = window._timelineData?.selectedStations || new Set(Object.keys(stationColors));

    let html = '<div style="position: relative;">';

    lotsData.forEach((lotData, lotIdx) => {
        html += `
            <div style="display: flex; align-items: center; margin-bottom: 6px; height: 24px;">
                <div style="width: 140px; flex-shrink: 0; font-family: monospace; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #666;" title="${lotData.lotId}">
                    ${lotData.lotId}
                </div>
                <div style="flex: 1; position: relative; height: 18px; background: #e9ecef; border-radius: 3px;">
        `;

        lotData.steps.forEach((step) => {
            if (!step.trackIn || step.trackIn <= 0) return;
            if (!selectedStations.has(step.station)) return;

            const left = ((step.trackIn - minTime) / timeRange) * 100;
            const width = Math.max(((step.trackOut - step.trackIn) / timeRange) * 100, 0.5);

            html += `
                <div style="position: absolute; left: ${left}%; width: ${width}%; height: 100%; background: ${step.color}; border-radius: 2px; ${step.isOngoing ? 'opacity: 0.6;' : ''}"
                     title="${step.station} - ${step.equipment || ''}"></div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    html += '</div>';
    return html;
}

function toggleStationFilter(station) {
    const data = window._timelineData;
    if (!data) return;

    if (data.selectedStations.has(station)) {
        data.selectedStations.delete(station);
    } else {
        data.selectedStations.add(station);
    }

    // Update UI
    const item = document.querySelector(`.station-filter-item[data-station="${station}"]`);
    if (item) {
        item.classList.toggle('active', data.selectedStations.has(station));
        item.style.opacity = data.selectedStations.has(station) ? '1' : '0.4';
    }

    // Re-render preview
    const preview = document.getElementById('timelinePreview');
    if (preview) {
        preview.innerHTML = renderTimelinePreview(data.lotsData, data.minTime, data.maxTime, data.stationColors);
    }
}

function selectAllStations() {
    const data = window._timelineData;
    if (!data) return;

    data.selectedStations = new Set(data.allStations);
    document.querySelectorAll('.station-filter-item').forEach(item => {
        item.classList.add('active');
        item.style.opacity = '1';
    });

    const preview = document.getElementById('timelinePreview');
    if (preview) {
        preview.innerHTML = renderTimelinePreview(data.lotsData, data.minTime, data.maxTime, data.stationColors);
    }
}

function deselectAllStations() {
    const data = window._timelineData;
    if (!data) return;

    data.selectedStations = new Set();
    document.querySelectorAll('.station-filter-item').forEach(item => {
        item.classList.remove('active');
        item.style.opacity = '0.4';
    });

    const preview = document.getElementById('timelinePreview');
    if (preview) {
        preview.innerHTML = renderTimelinePreview(data.lotsData, data.minTime, data.maxTime, data.stationColors);
    }
}

function openTimelinePopup() {
    const data = window._timelineData;
    if (!data) return;

    // Create popup overlay
    const popup = document.createElement('div');
    popup.id = 'timelinePopup';
    popup.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;';

    const popupContent = document.createElement('div');
    popupContent.style.cssText = 'background: white; border-radius: 12px; width: 95%; max-width: 1400px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,0.3);';

    popupContent.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 20px 25px; border-bottom: 1px solid #e0e0e0;">
            <div style="font-size: 18px; font-weight: 600; color: #333;">
                生產時間線
            </div>
            <div style="display: flex; align-items: center; gap: 20px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <label style="font-size: 13px; color: #666;">時間比例</label>
                    <input type="range" id="timelineScaleSlider" min="10" max="200" value="${data.pixelsPerHour}"
                           oninput="updateTimelineScale(this.value)" style="width: 120px;">
                    <span id="scaleValue" style="font-size: 13px; color: #666; min-width: 60px;">${data.pixelsPerHour}px/h</span>
                </div>
                <button onclick="closeTimelinePopup()" style="background: none; border: none; font-size: 28px; cursor: pointer; color: #999; line-height: 1;">&times;</button>
            </div>
        </div>
        <div id="popupTimelineContent" style="flex: 1; overflow: auto; padding: 20px 25px;"></div>
    `;

    popup.appendChild(popupContent);
    document.body.appendChild(popup);

    // Close on backdrop click
    popup.addEventListener('click', (e) => {
        if (e.target === popup) closeTimelinePopup();
    });

    // Close on Escape key
    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
            closeTimelinePopup();
            document.removeEventListener('keydown', escHandler);
        }
    });

    // Render full timeline
    renderFullTimeline(data.pixelsPerHour);
}

function closeTimelinePopup() {
    const popup = document.getElementById('timelinePopup');
    if (popup) {
        // Clear the popup's inner HTML first to help garbage collection
        const content = popup.querySelector('#popupTimelineContent');
        if (content) content.innerHTML = '';
        popup.remove();
    }
}

function updateTimelineScale(value) {
    const data = window._timelineData;
    if (!data) return;

    data.pixelsPerHour = parseInt(value);
    document.getElementById('scaleValue').textContent = value + 'px/h';

    renderFullTimeline(data.pixelsPerHour);
}

function renderFullTimeline(pixelsPerHour) {
    const data = window._timelineData;
    if (!data) return;

    const container = document.getElementById('popupTimelineContent');
    if (!container) return;

    const { lotsData, minTime, maxTime, stationColors, selectedStations } = data;
    const MS_PER_HOUR = 3600000;
    const totalHours = (maxTime - minTime) / MS_PER_HOUR;
    const timelineWidth = Math.max(800, totalHours * pixelsPerHour);

    let html = `
        <div style="overflow-x: auto;">
            <div style="width: ${timelineWidth + 180}px; min-width: 100%;">
                ${renderTimelineAxisFixed(minTime, maxTime, pixelsPerHour)}
                <div style="position: relative;">
    `;

    lotsData.forEach((lotData) => {
        html += `
            <div style="display: flex; align-items: stretch; margin-bottom: 12px;">
                <div style="width: 180px; flex-shrink: 0; padding-right: 15px; padding-top: 10px; font-family: monospace; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; position: sticky; left: 0; background: white; z-index: 5; color: #333;" title="${lotData.lotId}">
                    ${lotData.lotId}
                </div>
                <div style="width: ${timelineWidth}px; position: relative; min-height: 50px; background: #f8f9fa; border-radius: 4px;">
        `;

        lotData.steps.forEach((step, stepIdx) => {
            if (!step.trackIn || step.trackIn <= 0) return;
            if (!selectedStations.has(step.station)) return;

            const leftPx = ((step.trackIn - minTime) / MS_PER_HOUR) * pixelsPerHour;
            const durationHours = (step.trackOut - step.trackIn) / MS_PER_HOUR;
            const widthPx = Math.max(durationHours * pixelsPerHour, 40);

            const equipmentLabel = step.equipment || '';
            const durationStr = durationHours >= 1
                ? `${Math.floor(durationHours)}h ${Math.round((durationHours % 1) * 60)}m`
                : `${Math.round(durationHours * 60)}m`;
            const timeRangeStr = step.isOngoing ? '進行中' : formatDateTime(new Date(step.trackOut));
            const tooltipLines = [
                `${step.station} - ${equipmentLabel}`,
                `${formatDateTime(new Date(step.trackIn))} ~ ${timeRangeStr}`,
                `耗時: ${durationStr}`,
                `規格: ${step.spec}`
            ];

            html += `
                <div class="timeline-bar"
                     style="position: absolute; left: ${leftPx}px; width: ${widthPx}px; height: 100%; background: ${step.color}; border-radius: 4px; cursor: pointer; overflow: hidden; display: flex; flex-direction: column; justify-content: center; padding: 3px 6px; box-sizing: border-box; ${step.isOngoing ? 'background: repeating-linear-gradient(45deg, ' + step.color + ', ' + step.color + ' 5px, ' + step.color + '99 5px, ' + step.color + '99 10px);' : ''}"
                     title="${tooltipLines.join('&#10;')}"
                     onclick="showTimelineDetail('${lotData.containerId}', ${stepIdx}); closeTimelinePopup();">
                    <span style="font-size: 12px; color: white; text-shadow: 0 0 2px rgba(0,0,0,0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.3; font-weight: 500;">${equipmentLabel}</span>
                    <span style="font-size: 11px; color: rgba(255,255,255,0.9); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;">${step.station}</span>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    html += `
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function setTimelineScale(pixelsPerHour) {
    const data = window._timelineData;
    if (!data) return;

    // Update button states
    ['scale25', 'scale50', 'scale100', 'scale200'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.toggle('active', id === `scale${pixelsPerHour}`);
        }
    });

    const MS_PER_HOUR = 3600000;
    const { minTime, maxTime } = data;

    // Recalculate timeline width
    const totalHours = (maxTime - minTime) / MS_PER_HOUR;
    const timelineWidth = Math.max(800, totalHours * pixelsPerHour);

    // Update container width
    const inner = document.getElementById('timelineInner');
    if (inner) {
        inner.style.width = timelineWidth + 'px';

        // Update all bar widths (relative part)
        const barContainers = inner.querySelectorAll('.timeline-bar').forEach(bar => {
            const durationHours = parseFloat(bar.dataset.durationHours) || 0;
            const leftHours = (parseFloat(bar.style.left) / (data.pixelsPerHour || 50));
            const newLeft = leftHours * pixelsPerHour;
            const newWidth = Math.max(durationHours * pixelsPerHour, 30);

            bar.style.left = newLeft + 'px';
            bar.style.width = newWidth + 'px';
        });

        // Update time axis
        const axisContainer = inner.querySelector('.timeline-axis-container');
        if (axisContainer) {
            axisContainer.outerHTML = renderTimelineAxisFixed(minTime, maxTime, pixelsPerHour);
        }

        // Update lot row widths
        inner.querySelectorAll('.timeline-bar').forEach(bar => {
            const parent = bar.parentElement;
            if (parent) {
                parent.style.width = (timelineWidth - 180) + 'px';
            }
        });
    }

    // Update stored pixelsPerHour
    data.pixelsPerHour = pixelsPerHour;
}

function renderTimelineAxisFixed(minTime, maxTime, pixelsPerHour) {
    const MS_PER_HOUR = 3600000;
    const totalHours = (maxTime - minTime) / MS_PER_HOUR;
    const timelineWidth = totalHours * pixelsPerHour;

    // Generate tick marks - one per day or per 6 hours depending on scale
    const tickIntervalHours = pixelsPerHour >= 100 ? 6 : (pixelsPerHour >= 50 ? 12 : 24);
    const ticks = [];

    // Start from the first hour mark after minTime
    const startDate = new Date(minTime);
    startDate.setMinutes(0, 0, 0);
    let tickTime = startDate.getTime();
    if (tickTime < minTime) tickTime += MS_PER_HOUR;

    // Align to tick interval
    const tickHour = new Date(tickTime).getHours();
    const alignOffset = tickHour % tickIntervalHours;
    if (alignOffset > 0) {
        tickTime += (tickIntervalHours - alignOffset) * MS_PER_HOUR;
    }

    while (tickTime <= maxTime) {
        const date = new Date(tickTime);
        const pos = ((tickTime - minTime) / MS_PER_HOUR) * pixelsPerHour;
        const label = `${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:00`;
        ticks.push({ pos, label, isDay: date.getHours() === 0 });
        tickTime += tickIntervalHours * MS_PER_HOUR;
    }

    return `
        <div class="timeline-axis-container" style="position: relative; margin-left: 180px; height: 25px; border-bottom: 1px solid #e0e0e0; margin-bottom: 10px;">
            ${ticks.map(t => `
                <div style="position: absolute; left: ${t.pos}px; transform: translateX(-50%);">
                    <div style="font-family: monospace; font-size: 10px; color: ${t.isDay ? '#4e54c8' : '#888'}; font-weight: ${t.isDay ? '600' : '400'}; white-space: nowrap;">${t.label}</div>
                    <div style="position: absolute; left: 50%; width: 1px; height: 8px; background: ${t.isDay ? '#4e54c8' : '#ddd'}; top: 17px;"></div>
                </div>
            `).join('')}
        </div>
    `;
}

function showTimelineDetail(containerId, stepIndex) {
    // Find the lot and show its detail
    const lotIndex = QueryToolState.resolvedLots.findIndex(l => l.container_id === containerId);
    if (lotIndex >= 0) {
        selectLot(lotIndex);
        // Scroll to the history row
        setTimeout(() => {
            const row = document.getElementById(`history-row-${stepIndex}`);
            if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.style.background = '#fff3cd';
                setTimeout(() => { row.style.background = ''; }, 2000);
            }
        }, 300);
    }
}

async function showAdjacentLots(equipmentId, equipmentName, targetTime) {
    // Open modal or expand section to show adjacent lots
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content" style="width: 900px; max-width: 95%; max-height: 80vh; overflow-y: auto;">
            <div class="modal-header">
                <h3>前後批查詢</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
            </div>
            <div class="modal-body">
                <div class="info-box" style="margin-bottom: 15px;">
                    設備: ${equipmentName} | 基準時間: ${formatDateTime(targetTime)}
                </div>
                <div id="adjacentLotsContent">
                    <div class="loading"><div class="loading-spinner"></div></div>
                </div>
            </div>
        </div>
    `;

    // Add modal styles if not exists
    if (!document.getElementById('modal-styles')) {
        const style = document.createElement('style');
        style.id = 'modal-styles';
        style.textContent = `
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            }
            .modal-content {
                background: white;
                border-radius: 8px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 20px;
                border-bottom: 1px solid #e0e0e0;
            }
            .modal-header h3 {
                margin: 0;
                font-size: 18px;
            }
            .modal-close {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
            }
            .modal-close:hover {
                color: #333;
            }
            .modal-body {
                padding: 20px;
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(modal);

    // Load adjacent lots
    try {
        const result = await MesApi.get('/api/query-tool/adjacent-lots', {
            params: {
                equipment_id: equipmentId,
                target_time: targetTime,
                time_window: 24
            }
        });

        const content = document.getElementById('adjacentLotsContent');

        if (result.error) {
            content.innerHTML = `<div class="error">${result.error}</div>`;
            return;
        }

        if (!result.data || result.data.length === 0) {
            content.innerHTML = `<div class="empty-state"><p>無前後批資料</p></div>`;
            return;
        }

        let html = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>相對位置</th>
                            <th>LOT ID</th>
                            <th>產品類型</th>
                            <th>BOP</th>
                            <th>Wafer Lot</th>
                            <th>工單</th>
                            <th>批次號</th>
                            <th>上機時間</th>
                            <th>下機時間</th>
                            <th>上機數</th>
                            <th>下機數</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        result.data.forEach(lot => {
            const pos = lot.RELATIVE_POSITION;
            const posLabel = pos === 0 ? '目標批次' : (pos > 0 ? `+${pos}` : pos);
            const rowClass = pos === 0 ? 'style="background: #fff3cd;"' : '';

            html += `
                <tr ${rowClass}>
                    <td><strong>${posLabel}</strong></td>
                    <td>${lot.CONTAINERNAME || '-'}</td>
                    <td>${lot.PJ_TYPE || '-'}</td>
                    <td>${lot.PJ_BOP || '-'}</td>
                    <td>${lot.WAFER_LOT_ID || '-'}</td>
                    <td>${lot.PJ_WORKORDER || '-'}</td>
                    <td>${lot.FINISHEDRUNCARD || ''}</td>
                    <td>${formatDateTime(lot.TRACKINTIMESTAMP)}</td>
                    <td>${formatDateTime(lot.TRACKOUTTIMESTAMP)}</td>
                    <td>${lot.TRACKINQTY || ''}</td>
                    <td>${lot.TRACKOUTQTY || ''}</td>
                </tr>
            `;
        });

        html += `</tbody></table></div>`;
        content.innerHTML = html;

    } catch (error) {
        document.getElementById('adjacentLotsContent').innerHTML = `<div class="error">查詢失敗: ${error.message}</div>`;
    }
}

// ============================================================
// Workcenter Group Filter Functions
// ============================================================

async function loadWorkcenterGroups() {
    try {
        const result = await MesApi.get('/api/query-tool/workcenter-groups', {
            silent: true
        });
        if (result.error) {
            console.error('Failed to load workcenter groups:', result.error);
            return;
        }

        QueryToolState.workcenterGroups = result.data || [];
        console.log(`[QueryTool] Loaded ${QueryToolState.workcenterGroups.length} workcenter groups`);
    } catch (error) {
        console.error('Error loading workcenter groups:', error);
    }
}

function renderWorkcenterGroupSelector() {
    const container = document.getElementById('workcenterGroupSelector');
    if (!container) return;

    const groups = QueryToolState.workcenterGroups;
    const selected = QueryToolState.selectedWorkcenterGroups;
    const count = selected.size;

    let html = `
        <div class="wc-group-selector">
            <button type="button" class="wc-group-btn" onclick="toggleWorkcenterGroupDropdown()">
                <span id="wcGroupDisplay">${count === 0 ? '全部站點' : `${count} 個站點群組`}</span>
                <span class="wc-group-badge" id="wcGroupBadge" style="display: ${count > 0 ? 'inline-block' : 'none'};">${count}</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style="margin-left: auto;">
                    <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <div class="wc-group-dropdown" id="wcGroupDropdown">
                <div class="wc-group-header">
                    <label style="cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <input type="checkbox" id="wcGroupSelectAll" onchange="toggleAllWorkcenterGroups(this.checked)"
                               ${selected.size === groups.length && groups.length > 0 ? 'checked' : ''}>
                        全選
                    </label>
                    <span id="wcGroupSelectedCount">已選 ${count}</span>
                </div>
                <div class="wc-group-search">
                    <input type="text" placeholder="搜尋站點群組..." oninput="filterWorkcenterGroups(this.value)">
                </div>
                <div class="wc-group-list" id="wcGroupList">
    `;

    groups.forEach(group => {
        const isSelected = selected.has(group.name);
        html += `
            <div class="wc-group-item ${isSelected ? 'selected' : ''}" data-group="${group.name}">
                <label onclick="event.stopPropagation();">
                    <input type="checkbox" ${isSelected ? 'checked' : ''}
                           onchange="toggleWorkcenterGroup('${group.name}', this.checked)">
                    ${group.name}
                </label>
            </div>
        `;
    });

    html += `
                </div>
                <div class="wc-group-footer">
                    <button type="button" class="btn btn-sm btn-secondary" onclick="clearWorkcenterGroups()">清除</button>
                    <button type="button" class="btn btn-sm btn-primary" onclick="applyWorkcenterFilter()">套用篩選</button>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function toggleWorkcenterGroup(groupName, checked) {
    if (checked) {
        QueryToolState.selectedWorkcenterGroups.add(groupName);
    } else {
        QueryToolState.selectedWorkcenterGroups.delete(groupName);
    }
    updateWorkcenterGroupUI();
}

function toggleAllWorkcenterGroups(checked) {
    if (checked) {
        QueryToolState.workcenterGroups.forEach(g => {
            QueryToolState.selectedWorkcenterGroups.add(g.name);
        });
    } else {
        QueryToolState.selectedWorkcenterGroups.clear();
    }
    renderWorkcenterGroupSelector();
}

function clearWorkcenterGroups() {
    QueryToolState.selectedWorkcenterGroups.clear();
    renderWorkcenterGroupSelector();
}

function updateWorkcenterGroupUI() {
    const count = QueryToolState.selectedWorkcenterGroups.size;
    const display = document.getElementById('wcGroupDisplay');
    const badge = document.getElementById('wcGroupBadge');
    const countEl = document.getElementById('wcGroupSelectedCount');
    const selectAll = document.getElementById('wcGroupSelectAll');

    // Update item visual state
    document.querySelectorAll('.wc-group-item').forEach(item => {
        const groupName = item.dataset.group;
        const isSelected = QueryToolState.selectedWorkcenterGroups.has(groupName);
        item.classList.toggle('selected', isSelected);
        const checkbox = item.querySelector('input[type="checkbox"]');
        if (checkbox) checkbox.checked = isSelected;
    });

    // Update display text and badge
    if (display) {
        display.textContent = count === 0 ? '全部站點' : `${count} 個站點群組`;
    }
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
    if (countEl) {
        countEl.textContent = `已選 ${count}`;
    }
    if (selectAll) {
        selectAll.checked = count === QueryToolState.workcenterGroups.length && count > 0;
    }
}

function toggleWorkcenterGroupDropdown() {
    const dropdown = document.getElementById('wcGroupDropdown');
    if (dropdown) dropdown.classList.toggle('show');
}

function closeWorkcenterGroupDropdown() {
    const dropdown = document.getElementById('wcGroupDropdown');
    if (dropdown) dropdown.classList.remove('show');
}

function applyWorkcenterFilter() {
    // Close dropdown
    closeWorkcenterGroupDropdown();

    // Check if we have selected lots
    if (QueryToolState.timelineSelectedLots.size === 0) {
        Toast.warning('請先選擇批次');
        return;
    }

    const wcGroups = QueryToolState.selectedWorkcenterGroups;
    if (wcGroups.size > 0) {
        Toast.info(`套用 ${wcGroups.size} 個站點群組篩選...`);
    } else {
        Toast.info('顯示全部站點資料...');
    }

    // Re-run confirmLotSelection to apply the filter
    confirmLotSelection();
}

function filterWorkcenterGroups(searchText) {
    const items = document.querySelectorAll('.wc-group-item');
    const search = searchText.toLowerCase();

    items.forEach(item => {
        const groupName = item.dataset.group.toLowerCase();
        item.style.display = groupName.includes(search) ? 'flex' : 'none';
    });
}

function showWorkcenterGroupSelector() {
    // Show the entire selection bar
    const selectionBar = document.getElementById('selectionBar');
    if (selectionBar) {
        selectionBar.style.display = 'flex';
    }

    // Render the workcenter group selector if groups are available
    if (QueryToolState.workcenterGroups.length > 0) {
        renderWorkcenterGroupSelector();
    }
}

// ============================================================
// Equipment Query Functions
// ============================================================

async function loadEquipments() {
    try {
        const data = await MesApi.get('/api/query-tool/equipment-list');
        if (data.error) {
            document.getElementById('equipmentList').innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        QueryToolState.allEquipments = data.data;
        renderEquipmentList(data.data);
    } catch (error) {
        document.getElementById('equipmentList').innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function renderEquipmentList(equipments) {
    const container = document.getElementById('equipmentList');

    if (!equipments || equipments.length === 0) {
        container.innerHTML = '<div class="empty-state">無設備資料</div>';
        return;
    }

    let html = '';
    let currentWorkcenter = null;

    equipments.forEach(eq => {
        const isSelected = QueryToolState.selectedEquipments.has(eq.RESOURCEID);

        // Group header
        if (eq.WORKCENTERNAME !== currentWorkcenter) {
            currentWorkcenter = eq.WORKCENTERNAME;
            html += `<div style="padding: 8px 15px; background: #f0f0f0; font-weight: 600; font-size: 12px; color: #666;">${currentWorkcenter || '未分類'}</div>`;
        }

        html += `
            <div class="equipment-item ${isSelected ? 'selected' : ''}" onclick="toggleEquipment('${eq.RESOURCEID}')">
                <input type="checkbox" ${isSelected ? 'checked' : ''} onclick="event.stopPropagation(); toggleEquipment('${eq.RESOURCEID}')">
                <div class="equipment-info">
                    <div class="equipment-name">${eq.RESOURCENAME}</div>
                    <div class="equipment-workcenter">${eq.RESOURCEFAMILYNAME || ''}</div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function toggleEquipmentDropdown() {
    const dropdown = document.getElementById('equipmentDropdown');
    dropdown.classList.toggle('show');
}

function filterEquipments(query) {
    const q = query.toLowerCase();
    const filtered = QueryToolState.allEquipments.filter(eq =>
        (eq.RESOURCENAME && eq.RESOURCENAME.toLowerCase().includes(q)) ||
        (eq.WORKCENTERNAME && eq.WORKCENTERNAME.toLowerCase().includes(q)) ||
        (eq.RESOURCEFAMILYNAME && eq.RESOURCEFAMILYNAME.toLowerCase().includes(q))
    );
    renderEquipmentList(filtered);
}

function toggleEquipment(resourceId) {
    if (QueryToolState.selectedEquipments.has(resourceId)) {
        QueryToolState.selectedEquipments.delete(resourceId);
    } else {
        if (QueryToolState.selectedEquipments.size >= 20) {
            Toast.warning('最多只能選擇 20 台設備');
            return;
        }
        QueryToolState.selectedEquipments.add(resourceId);
    }
    updateSelectedDisplay();

    // Re-render with current filter
    const search = document.querySelector('.equipment-search');
    if (search && search.value) {
        filterEquipments(search.value);
    } else {
        renderEquipmentList(QueryToolState.allEquipments);
    }
}

function updateSelectedDisplay() {
    const display = document.getElementById('equipmentDisplay');
    const count = document.getElementById('selectedCount');

    if (QueryToolState.selectedEquipments.size === 0) {
        display.textContent = '點擊選擇設備...';
        count.textContent = '';
    } else if (QueryToolState.selectedEquipments.size <= 3) {
        const names = QueryToolState.allEquipments
            .filter(eq => QueryToolState.selectedEquipments.has(eq.RESOURCEID))
            .map(eq => eq.RESOURCENAME)
            .join(', ');
        display.textContent = names;
        count.textContent = `已選擇 ${QueryToolState.selectedEquipments.size} 台設備`;
    } else {
        display.textContent = `已選擇 ${QueryToolState.selectedEquipments.size} 台設備`;
        count.textContent = '';
    }
}

function setLast30Days() {
    const today = new Date();
    const past = new Date();
    past.setDate(today.getDate() - 30);

    document.getElementById('dateFrom').value = past.toISOString().split('T')[0];
    document.getElementById('dateTo').value = today.toISOString().split('T')[0];
}

async function executeEquipmentQuery() {
    if (QueryToolState.selectedEquipments.size === 0) {
        Toast.error('請選擇至少一台設備');
        return;
    }

    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (!dateFrom || !dateTo) {
        Toast.error('請指定日期範圍');
        return;
    }

    // Validate date range
    const from = new Date(dateFrom);
    const to = new Date(dateTo);

    if (to < from) {
        Toast.error('結束日期不可早於起始日期');
        return;
    }

    const daysDiff = (to - from) / (1000 * 60 * 60 * 24);
    if (daysDiff > 90) {
        Toast.error('日期範圍不可超過 90 天');
        return;
    }

    // Clear previous equipment results to free memory
    QueryToolState.equipmentResults = null;
    const eqContent = document.getElementById('eqResultsContent');
    if (eqContent) eqContent.innerHTML = '';

    // Show loading
    document.getElementById('eqEmptyState').style.display = 'none';
    document.getElementById('eqResultsContent').style.display = 'block';
    document.getElementById('eqResultsContent').innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <br>查詢中...
        </div>
    `;

    document.getElementById('eqQueryBtn').disabled = true;

    const equipmentIds = Array.from(QueryToolState.selectedEquipments);
    const equipmentNames = QueryToolState.allEquipments
        .filter(eq => QueryToolState.selectedEquipments.has(eq.RESOURCEID))
        .map(eq => eq.RESOURCENAME);

    try {
        // Load status hours first
        const statusResult = await MesApi.post('/api/query-tool/equipment-period', {
            equipment_ids: equipmentIds,
            equipment_names: equipmentNames,
            start_date: dateFrom,
            end_date: dateTo,
            query_type: 'status_hours'
        });

        QueryToolState.equipmentResults = {
            status_hours: statusResult,
            equipment_ids: equipmentIds,
            equipment_names: equipmentNames,
            date_range: { start: dateFrom, end: dateTo }
        };

        renderEquipmentResults();

    } catch (error) {
        document.getElementById('eqResultsContent').innerHTML = `<div class="error">查詢失敗: ${error.message}</div>`;
    } finally {
        document.getElementById('eqQueryBtn').disabled = false;
    }
}

function renderEquipmentResults() {
    const results = QueryToolState.equipmentResults;
    const content = document.getElementById('eqResultsContent');

    let html = `
        <div class="result-header">
            <div class="result-info">
                ${QueryToolState.selectedEquipments.size} 台設備 | ${results.date_range.start} ~ ${results.date_range.end}
            </div>
        </div>

        <div class="assoc-tabs" style="margin-bottom: 20px;">
            <button class="assoc-tab active" onclick="loadEquipmentTab('status_hours', this)">狀態時數</button>
            <button class="assoc-tab" onclick="loadEquipmentTab('lots', this)">批次清單</button>
            <button class="assoc-tab" onclick="loadEquipmentTab('materials', this)">物料消耗</button>
            <button class="assoc-tab" onclick="loadEquipmentTab('rejects', this)">不良統計</button>
            <button class="assoc-tab" onclick="loadEquipmentTab('jobs', this)">JOB 紀錄</button>
        </div>

        <div id="eqTabContent"></div>
    `;

    content.innerHTML = html;

    // Render initial tab
    renderEquipmentTab('status_hours', results.status_hours);
}

async function loadEquipmentTab(tabType, tabElement) {
    // Update tab states
    document.querySelectorAll('#eqResultsContent .assoc-tab').forEach(t => t.classList.remove('active'));
    if (tabElement) tabElement.classList.add('active');

    const content = document.getElementById('eqTabContent');
    content.innerHTML = `<div class="loading"><div class="loading-spinner"></div></div>`;

    const results = QueryToolState.equipmentResults;

    // Check if already loaded
    if (results[tabType]) {
        renderEquipmentTab(tabType, results[tabType]);
        return;
    }

    try {
        const result = await MesApi.post('/api/query-tool/equipment-period', {
            equipment_ids: results.equipment_ids,
            equipment_names: results.equipment_names,
            start_date: results.date_range.start,
            end_date: results.date_range.end,
            query_type: tabType
        });

        results[tabType] = result;
        renderEquipmentTab(tabType, result);

    } catch (error) {
        content.innerHTML = `<div class="error">載入失敗: ${error.message}</div>`;
    }
}

function renderEquipmentTab(tabType, result) {
    const content = document.getElementById('eqTabContent');

    if (result.error) {
        content.innerHTML = `<div class="error">${result.error}</div>`;
        return;
    }

    if (!result.data || result.data.length === 0) {
        content.innerHTML = `<div class="empty-state"><p>無資料</p></div>`;
        return;
    }

    const data = result.data;

    // Define columns based on tab type
    const columnDefs = {
        'status_hours': {
            cols: ['RESOURCENAME', 'PRD_HOURS', 'SBY_HOURS', 'UDT_HOURS', 'SDT_HOURS', 'EGT_HOURS', 'NST_HOURS', 'TOTAL_HOURS', 'OU_PERCENT'],
            labels: { RESOURCENAME: '設備名稱', PRD_HOURS: '生產', SBY_HOURS: '待機', UDT_HOURS: '非計畫停機', SDT_HOURS: '計畫停機', EGT_HOURS: '工程', NST_HOURS: '非排程', TOTAL_HOURS: '總時數', OU_PERCENT: 'OU%' }
        },
        'lots': {
            cols: ['EQUIPMENTNAME', 'WORKCENTERNAME', 'CONTAINERNAME', 'PJ_TYPE', 'PJ_BOP', 'WAFER_LOT_ID', 'FINISHEDRUNCARD', 'SPECNAME', 'TRACKINTIMESTAMP', 'TRACKOUTTIMESTAMP', 'TRACKINQTY', 'TRACKOUTQTY'],
            labels: { EQUIPMENTNAME: '設備', WORKCENTERNAME: '站點', CONTAINERNAME: 'LOT ID', PJ_TYPE: '產品類型', PJ_BOP: 'BOP', WAFER_LOT_ID: 'Wafer Lot', FINISHEDRUNCARD: '批次號', SPECNAME: '規格', TRACKINTIMESTAMP: '上機時間', TRACKOUTTIMESTAMP: '下機時間', TRACKINQTY: '上機數', TRACKOUTQTY: '下機數' }
        },
        'materials': {
            cols: ['EQUIPMENTNAME', 'MATERIALPARTNAME', 'TOTAL_CONSUMED', 'LOT_COUNT'],
            labels: { EQUIPMENTNAME: '設備', MATERIALPARTNAME: '物料名稱', TOTAL_CONSUMED: '消耗總量', LOT_COUNT: '批次數' }
        },
        'rejects': {
            cols: ['EQUIPMENTNAME', 'LOSSREASONNAME', 'TOTAL_DEFECT_QTY', 'TOTAL_REJECT_QTY', 'AFFECTED_LOT_COUNT'],
            labels: { EQUIPMENTNAME: '設備', LOSSREASONNAME: '損失原因', TOTAL_DEFECT_QTY: '不良數量', TOTAL_REJECT_QTY: 'REJECT數量', AFFECTED_LOT_COUNT: '影響批次' }
        },
        'jobs': {
            cols: ['RESOURCENAME', 'JOBID', 'JOBSTATUS', 'JOBMODELNAME', 'CREATEDATE', 'COMPLETEDATE', 'CAUSECODENAME', 'REPAIRCODENAME'],
            labels: { RESOURCENAME: '設備', JOBID: 'JOB ID', JOBSTATUS: '狀態', JOBMODELNAME: '類型', CREATEDATE: '建立時間', COMPLETEDATE: '完成時間', CAUSECODENAME: '原因代碼', REPAIRCODENAME: '維修代碼' }
        }
    };

    const def = columnDefs[tabType] || { cols: Object.keys(data[0]), labels: {} };

    // Add export button
    let html = `
        <div style="text-align: right; margin-bottom: 10px;">
            <button class="btn btn-success btn-sm" onclick="exportEquipmentTab('${tabType}')">匯出 CSV</button>
        </div>
    `;

    // Show totals for status_hours
    if (tabType === 'status_hours' && result.totals) {
        const t = result.totals;
        html += `
            <div class="info-box" style="margin-bottom: 15px;">
                總計: PRD ${t.PRD_HOURS?.toFixed(1) || 0}h | SBY ${t.SBY_HOURS?.toFixed(1) || 0}h |
                UDT ${t.UDT_HOURS?.toFixed(1) || 0}h | OU% ${t.OU_PERCENT?.toFixed(1) || 0}%
            </div>
        `;
    }

    html += `<div class="table-container" style="max-height: 500px;"><table><thead><tr>`;

    def.cols.forEach(col => {
        html += `<th>${def.labels[col] || col}</th>`;
    });
    html += `</tr></thead><tbody>`;

    data.forEach(row => {
        html += `<tr>`;
        def.cols.forEach(col => {
            let value = row[col];
            if (col.includes('DATE') || col.includes('TIMESTAMP')) {
                value = formatDateTime(value);
            }
            if (col === 'OU_PERCENT' && value !== null) {
                value = `${value}%`;
            }
            if ((col.endsWith('_HOURS') || col === 'TOTAL_CONSUMED') && value !== null) {
                value = Number(value).toFixed(2);
            }
            html += `<td>${value !== null && value !== undefined ? value : ''}</td>`;
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>`;
    content.innerHTML = html;
}

// ============================================================
// Export Functions
// ============================================================

async function exportLotResults() {
    if (QueryToolState.resolvedLots.length === 0) {
        Toast.error('無資料可匯出');
        return;
    }

    const lot = QueryToolState.resolvedLots[QueryToolState.selectedLotIndex];

    try {
        const response = await fetch('/api/query-tool/export-csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                export_type: 'lot_history',
                params: { container_id: lot.container_id }
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || '匯出失敗');
        }

        downloadBlob(response, `lot_history_${lot.lot_id || lot.input_value}.csv`);
        Toast.success('CSV 匯出完成');

    } catch (error) {
        Toast.error('匯出失敗: ' + error.message);
    }
}

async function exportCombinedResults() {
    const selectedIndices = QueryToolState.currentSelectedIndices || [];
    if (selectedIndices.length === 0) {
        Toast.error('無資料可匯出');
        return;
    }

    // Collect all history data
    const lots = QueryToolState.resolvedLots;
    const allHistory = [];

    selectedIndices.forEach(idx => {
        const lot = lots[idx];
        const history = QueryToolState.lotHistories[lot.container_id] || [];
        history.forEach(step => {
            allHistory.push({
                LOT_ID: lot.lot_id || lot.input_value,
                ...step
            });
        });
    });

    if (allHistory.length === 0) {
        Toast.error('無資料可匯出');
        return;
    }

    // Generate CSV
    const headers = ['LOT_ID', 'WORKCENTERNAME', 'EQUIPMENTNAME', 'SPECNAME', 'PJ_TYPE', 'PJ_BOP', 'WAFER_LOT_ID', 'TRACKINTIMESTAMP', 'TRACKOUTTIMESTAMP', 'TRACKINQTY', 'TRACKOUTQTY'];
    let csv = headers.join(',') + '\n';

    allHistory.forEach(row => {
        csv += headers.map(h => {
            let val = row[h] || '';
            if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
                val = '"' + val.replace(/"/g, '""') + '"';
            }
            return val;
        }).join(',') + '\n';
    });

    // Download
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `combined_lot_history_${selectedIndices.length}lots.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    Toast.success('CSV 匯出完成');
}

// Export Production History (拆併批紀錄)
function exportProductionHistory(mode = 'single') {
    let productionHistory = [];
    let filename = 'production_split_merge_history';

    if (mode === 'combined') {
        // Get from combined splits data
        productionHistory = QueryToolState.combinedSplitsData?.production_history || [];
        const selectedCount = (QueryToolState.currentSelectedIndices || []).length;
        filename = `production_split_merge_history_${selectedCount}lots`;
    } else {
        // Get from current LOT's splits data (cached in lotAssociations)
        const containerId = QueryToolState.currentContainerId;
        const cacheKey = `${containerId}_splits`;
        const splitsData = QueryToolState.lotAssociations?.[cacheKey] || {};
        productionHistory = splitsData.production_history || [];
        const lotId = QueryToolState.resolvedLots?.find(l => l.container_id === containerId)?.lot_id || containerId;
        filename = `production_split_merge_history_${lotId}`;
    }

    if (!productionHistory || productionHistory.length === 0) {
        Toast.error('無生產拆併批紀錄可匯出');
        return;
    }

    // Generate CSV
    const headers = ['LOT_ID', '操作類型', '來源批次', '目標批次', '數量', '時間'];
    const keys = ['LOT_ID', 'operation_type_display', 'source_lot', 'target_lot', 'target_qty', 'txn_date'];
    let csv = headers.join(',') + '\n';

    productionHistory.forEach(row => {
        csv += keys.map(k => {
            let val = row[k] || '';
            if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
                val = '"' + val.replace(/"/g, '""') + '"';
            }
            return val;
        }).join(',') + '\n';
    });

    // Download
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    Toast.success('CSV 匯出完成');
}

// Export Serial Numbers (成品流水號對應)
function exportSerialNumbers(mode = 'single') {
    let serialNumbers = [];
    let filename = 'serial_number_mapping';

    if (mode === 'combined') {
        // Get from combined splits data
        serialNumbers = QueryToolState.combinedSplitsData?.serial_numbers || [];
        const selectedCount = (QueryToolState.currentSelectedIndices || []).length;
        filename = `serial_number_mapping_${selectedCount}lots`;
    } else {
        // Get from current LOT's splits data (cached in lotAssociations)
        const containerId = QueryToolState.currentContainerId;
        const cacheKey = `${containerId}_splits`;
        const splitsData = QueryToolState.lotAssociations?.[cacheKey] || {};
        serialNumbers = splitsData.serial_numbers || [];
        const lotId = QueryToolState.resolvedLots?.find(l => l.container_id === containerId)?.lot_id || containerId;
        filename = `serial_number_mapping_${lotId}`;
    }

    if (!serialNumbers || serialNumbers.length === 0) {
        Toast.error('無成品流水號對應資料可匯出');
        return;
    }

    // Flatten serial numbers data
    const flatData = [];
    serialNumbers.forEach(snGroup => {
        const sn = snGroup.serial_number || '';
        const totalDie = snGroup.total_good_die || 0;
        (snGroup.lots || []).forEach(lot => {
            flatData.push({
                serial_number: sn,
                total_good_die: totalDie,
                lot_id: lot.lot_id || '',
                combine_ratio_pct: lot.combine_ratio_pct || '',
                good_die_qty: lot.good_die_qty || 0
            });
        });
    });

    if (flatData.length === 0) {
        Toast.error('無成品流水號對應資料可匯出');
        return;
    }

    // Generate CSV
    const headers = ['流水號', '總 Good Die', 'LOT ID', '佔比', 'Good Die 數'];
    const keys = ['serial_number', 'total_good_die', 'lot_id', 'combine_ratio_pct', 'good_die_qty'];
    let csv = headers.join(',') + '\n';

    flatData.forEach(row => {
        csv += keys.map(k => {
            let val = row[k] || '';
            if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
                val = '"' + val.replace(/"/g, '""') + '"';
            }
            return val;
        }).join(',') + '\n';
    });

    // Download
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    Toast.success('CSV 匯出完成');
}

async function exportEquipmentTab(tabType) {
    const results = QueryToolState.equipmentResults;

    if (!results || !results[tabType] || !results[tabType].data) {
        Toast.error('無資料可匯出');
        return;
    }

    try {
        const params = {
            start_date: results.date_range.start,
            end_date: results.date_range.end
        };

        if (tabType === 'materials' || tabType === 'rejects') {
            params.equipment_names = results.equipment_names;
        } else {
            params.equipment_ids = results.equipment_ids;
        }

        const response = await fetch('/api/query-tool/export-csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                export_type: `equipment_${tabType}`,
                params: params
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || '匯出失敗');
        }

        downloadBlob(response, `equipment_${tabType}.csv`);
        Toast.success('CSV 匯出完成');

    } catch (error) {
        Toast.error('匯出失敗: ' + error.message);
    }
}

async function downloadBlob(response, filename) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// ============================================================
// Tab Navigation (Legacy - kept for compatibility)
// ============================================================

function switchMainTab(tabId) {
    // This function is kept for compatibility but the main UI now uses
    // query mode switching (batch vs equipment) instead of tabs
}

// ============================================================
// Utility Functions
// ============================================================

function formatDateTime(dateInput) {
    if (!dateInput) return '';

    // Handle Date objects
    if (dateInput instanceof Date) {
        const y = dateInput.getFullYear();
        const m = (dateInput.getMonth() + 1).toString().padStart(2, '0');
        const d = dateInput.getDate().toString().padStart(2, '0');
        const h = dateInput.getHours().toString().padStart(2, '0');
        const min = dateInput.getMinutes().toString().padStart(2, '0');
        const s = dateInput.getSeconds().toString().padStart(2, '0');
        return `${y}-${m}-${d} ${h}:${min}:${s}`;
    }

    // Handle timestamps (numbers)
    if (typeof dateInput === 'number') {
        return formatDateTime(new Date(dateInput));
    }

    // Handle strings
    if (typeof dateInput === 'string') {
        return dateInput.replace('T', ' ').substring(0, 19);
    }

    return '';
}

function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

const __QUERY_TOOL_GLOBAL_FNS = {
    applyWorkcenterFilter,
    clearQueryState,
    clearWorkcenterGroups,
    closeTimelinePopup,
    closeWorkcenterGroupDropdown,
    confirmLotSelection,
    deselectAllStations,
    downloadBlob,
    executeEquipmentQuery,
    executeLotQuery,
    exportCombinedResults,
    exportEquipmentTab,
    exportLotResults,
    exportProductionHistory,
    exportSerialNumbers,
    filterEquipments,
    filterWorkcenterGroups,
    formatDateTime,
    getAssocLabel,
    hideTimeline,
    loadAssociation,
    loadCombinedAssociation,
    loadEquipmentTab,
    loadEquipments,
    loadLotHistory,
    loadWorkcenterGroups,
    openTimelinePopup,
    parseInputValues,
    renderAssociation,
    renderCombinedAssociation,
    renderCombinedLotView,
    renderCombinedSplitsAssociation,
    renderEquipmentList,
    renderEquipmentResults,
    renderEquipmentTab,
    renderFullTimeline,
    renderLotDetail,
    renderLotResults,
    renderSplitsAssociation,
    renderTimeline,
    renderTimelineAxisFixed,
    renderTimelinePreview,
    renderWorkcenterGroupSelector,
    selectAllStations,
    selectLot,
    selectLotFromDropdown,
    setLast30Days,
    setQueryType,
    setTimelineScale,
    showAdjacentLots,
    showLotSelector,
    showTimeline,
    showTimelineDetail,
    showWorkcenterGroupSelector,
    switchMainTab,
    switchQueryMode,
    toggleAllLotsForTimeline,
    toggleAllLotsInSelector,
    toggleAllWorkcenterGroups,
    toggleEquipment,
    toggleEquipmentDropdown,
    toggleLotForTimeline,
    toggleLotInSelector,
    toggleLotSelector,
    toggleStationFilter,
    toggleWorkcenterGroup,
    toggleWorkcenterGroupDropdown,
    truncateText,
    updateLotInfoBar,
    updateLotSelectorCount,
    updateSelectedDisplay,
    updateTimelineButton,
    updateTimelineScale,
    updateWorkcenterGroupUI,
};

Object.assign(window, __QUERY_TOOL_GLOBAL_FNS);
