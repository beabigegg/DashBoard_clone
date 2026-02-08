import { ensureMesApiAvailable } from '../core/api.js';
import { getPageContract } from '../core/field-contracts.js';
import { buildResourceKpiFromHours } from '../core/compute.js';
import { groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();
window.__MES_FRONTEND_CORE__ = { buildResourceKpiFromHours, groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText };
window.__FIELD_CONTRACTS__ = window.__FIELD_CONTRACTS__ || {};
window.__FIELD_CONTRACTS__['tables:result_table'] = getPageContract('tables', 'result_table');


        let currentTable = null;
        let currentDisplayName = null;
        let currentTimeField = null;
        let currentColumns = [];
        let currentFilters = {};

        function toFilterInputId(column) {
            return `filter_${encodeURIComponent(safeText(column))}`;
        }

        function toJsSingleQuoted(value) {
            return safeText(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        }

        async function loadTableData(tableName, displayName, timeField) {
            // Mark current selected table
            document.querySelectorAll('.table-card').forEach(card => {
                card.classList.remove('active');
            });
            event.currentTarget.classList.add('active');

            currentTable = tableName;
            currentDisplayName = displayName;
            currentTimeField = timeField || null;
            currentFilters = {};

            const viewer = document.getElementById('dataViewer');
            const title = document.getElementById('viewerTitle');
            const content = document.getElementById('tableContent');
            const statsContainer = document.getElementById('statsContainer');

            viewer.classList.add('active');
            title.textContent = `正在載入: ${displayName}`;
            content.innerHTML = '<div class="loading">正在載入欄位資訊...</div>';
            statsContainer.innerHTML = '';

            viewer.scrollIntoView({ behavior: 'smooth', block: 'start' });

            try {
                const data = await MesApi.post('/api/get_table_columns', { table_name: tableName });

                if (data.error) {
                    content.innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                currentColumns = data.columns;
                title.textContent = `${displayName} (${currentColumns.length} 欄位)`;

                renderFilterControls();
            } catch (error) {
                content.innerHTML = `<div class="error">請求失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        function renderFilterControls() {
            const statsContainer = document.getElementById('statsContainer');
            const content = document.getElementById('tableContent');

            statsContainer.innerHTML = `
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-label">表名</div>
                        <div class="stat-value" style="font-size: 14px;">${escapeHtml(currentTable)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">欄位數</div>
                        <div class="stat-value">${currentColumns.length}</div>
                    </div>
                    <span class="filter-hint">在下方輸入框填入篩選條件 (模糊匹配)</span>
                    <button class="query-btn" onclick="executeQuery()">查詢</button>
                    <button class="clear-btn" onclick="clearFilters()">清除篩選</button>
                </div>
                <div id="activeFilters" class="active-filters"></div>
            `;

            let html = '<table><thead>';
            html += '<tr>';
            currentColumns.forEach(col => {
                html += `<th>${escapeHtml(col)}</th>`;
            });
            html += '</tr>';

            html += '<tr class="filter-row">';
            currentColumns.forEach(col => {
                const filterId = toFilterInputId(col);
                const jsCol = toJsSingleQuoted(col);
                html += `<th><input type="text" id="${filterId}" placeholder="篩選..." onkeypress="handleFilterKeypress(event)" onchange="updateFilter('${jsCol}', this.value)"></th>`;
            });
            html += '</tr>';

            html += '</thead><tbody id="dataBody">';
            html += '<tr><td colspan="' + currentColumns.length + '" style="text-align: center; padding: 40px; color: #666;">請輸入篩選條件後點擊「查詢」，或直接點擊「查詢」載入最後 1000 筆資料</td></tr>';
            html += '</tbody></table>';

            content.innerHTML = html;
        }

        function updateFilter(column, value) {
            if (value && value.trim()) {
                currentFilters[column] = value.trim();
            } else {
                delete currentFilters[column];
            }
            renderActiveFilters();
        }

        function renderActiveFilters() {
            const container = document.getElementById('activeFilters');
            if (!container) return;

            const filterKeys = Object.keys(currentFilters);
            if (filterKeys.length === 0) {
                container.innerHTML = '';
                return;
            }

            let html = '';
            filterKeys.forEach(col => {
                html += `<span class="filter-tag">${escapeHtml(col)}: ${escapeHtml(currentFilters[col])} <span class="remove" onclick="removeFilter('${toJsSingleQuoted(col)}')">&times;</span></span>`;
            });
            container.innerHTML = html;
        }

        function removeFilter(column) {
            delete currentFilters[column];
            const input = document.getElementById(toFilterInputId(column));
            if (input) input.value = '';
            renderActiveFilters();
        }

        function clearFilters() {
            currentFilters = {};
            currentColumns.forEach(col => {
                const input = document.getElementById(toFilterInputId(col));
                if (input) input.value = '';
            });
            renderActiveFilters();
        }

        function handleFilterKeypress(event) {
            if (event.key === 'Enter') {
                executeQuery();
            }
        }

        async function executeQuery() {
            const title = document.getElementById('viewerTitle');
            const tbody = document.getElementById('dataBody');

            currentFilters = {};
            currentColumns.forEach(col => {
                const input = document.getElementById(toFilterInputId(col));
                if (input && input.value.trim()) {
                    currentFilters[col] = input.value.trim();
                }
            });
            renderActiveFilters();

            title.textContent = `正在查詢: ${currentDisplayName}`;
            tbody.innerHTML = `<tr><td colspan="${currentColumns.length}" class="loading">正在查詢資料...</td></tr>`;

            try {
                const data = await MesApi.post('/api/query_table', {
                    table_name: currentTable,
                    limit: 1000,
                    time_field: currentTimeField,
                    filters: Object.keys(currentFilters).length > 0 ? currentFilters : null
                });

                if (data.error) {
                    tbody.innerHTML = `<tr><td colspan="${currentColumns.length}" class="error">${escapeHtml(data.error)}</td></tr>`;
                    return;
                }

                const filterCount = Object.keys(currentFilters).length;
                const filterText = filterCount > 0 ? ` [${filterCount} 個篩選]` : '';
                title.textContent = `${currentDisplayName} (${data.row_count} 筆)${filterText}`;

                if (data.data.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="${currentColumns.length}" style="text-align: center; padding: 40px; color: #999;">查無資料</td></tr>`;
                    return;
                }

                let html = '';
                data.data.forEach(row => {
                    html += '<tr>';
                    currentColumns.forEach(col => {
                        const value = row[col];
                        if (value === null || value === undefined) {
                            html += '<td><i style="color: #999;">NULL</i></td>';
                        } else {
                            html += `<td>${escapeHtml(safeText(value))}</td>`;
                        }
                    });
                    html += '</tr>';
                });
                tbody.innerHTML = html;
            } catch (error) {
                tbody.innerHTML = `<tr><td colspan="${currentColumns.length}" class="error">請求失敗: ${escapeHtml(error.message)}</td></tr>`;
            }
        }

        function closeViewer() {
            document.getElementById('dataViewer').classList.remove('active');
            document.querySelectorAll('.table-card').forEach(card => {
                card.classList.remove('active');
            });
            currentTable = null;
            currentColumns = [];
            currentFilters = {};
        }
    

Object.assign(window, {
loadTableData,
renderFilterControls,
updateFilter,
renderActiveFilters,
removeFilter,
clearFilters,
handleFilterKeypress,
executeQuery,
closeViewer,
});
