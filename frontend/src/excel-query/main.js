import { ensureMesApiAvailable } from '../core/api.js';
import { getPageContract } from '../core/field-contracts.js';
import { buildResourceKpiFromHours } from '../core/compute.js';
import { groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();
window.__MES_FRONTEND_CORE__ = { buildResourceKpiFromHours, groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText };
window.__FIELD_CONTRACTS__ = window.__FIELD_CONTRACTS__ || {};
window.__FIELD_CONTRACTS__['excel_query:result_table'] = getPageContract('excel_query', 'result_table');


        // State
        let excelColumns = [];
        let excelColumnTypes = {};  // { columnName: { detected_type, type_label } }
        let searchValues = [];
        let tableColumns = [];      // Array of column names (for backward compat)
        let tableColumnsMeta = [];  // Array of { name, data_type, is_date, is_number }
        let tableMetadata = null;   // Full table metadata including time_field, row_count
        let queryResult = null;

        // Step 1: Upload Excel
        async function uploadExcel() {
            const fileInput = document.getElementById('excelFile');
            const file = fileInput.files[0];

            if (!file) {
                alert('請選擇檔案');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            document.getElementById('uploadInfo').innerHTML = '<div class="loading"><div class="loading-spinner"></div><br>上傳中...</div>';

            try {
                // Note: File upload uses native fetch since MesApi doesn't support FormData
                const response = await fetch('/api/excel-query/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (data.error) {
                    document.getElementById('uploadInfo').innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                excelColumns = data.columns;
                document.getElementById('uploadInfo').innerHTML = `
                    <div class="info-box">
                        檔案上傳成功！共 ${data.total_rows} 行，${data.columns.length} 欄
                    </div>
                `;

                renderPreviewTable(data.columns, data.preview);

                const select = document.getElementById('excelColumn');
                select.innerHTML = '<option value="">-- 請選擇 --</option>';
                excelColumns.forEach(col => {
                    select.innerHTML += `<option value="${escapeHtml(col)}">${escapeHtml(col)}</option>`;
                });

                document.getElementById('step2').classList.remove('disabled');
                loadTables();

            } catch (error) {
                document.getElementById('uploadInfo').innerHTML = `<div class="error">上傳失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        function renderPreviewTable(columns, data) {
            if (!data || data.length === 0) return;

            let html = '<table class="preview-table"><thead><tr>';
            columns.forEach(col => {
                html += `<th>${escapeHtml(col)}</th>`;
            });
            html += '</tr></thead><tbody>';

            data.forEach(row => {
                html += '<tr>';
                columns.forEach(col => {
                    const val = row[col] !== null && row[col] !== undefined ? row[col] : '';
                    const textVal = safeText(val);
                    const escaped = escapeHtml(textVal);
                    html += `<td title="${escaped}">${escaped}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';

            document.getElementById('previewTable').innerHTML = html;
        }

        // Step 2: Load column values
        async function loadColumnValues() {
            const column = document.getElementById('excelColumn').value;
            if (!column) {
                searchValues = [];
                document.getElementById('columnInfo').innerHTML = '';
                return;
            }

            document.getElementById('columnInfo').innerHTML = '<div class="loading"><div class="loading-spinner"></div><br>讀取中...</div>';

            try {
                // Get column values
                const data = await MesApi.post('/api/excel-query/column-values', { column_name: column });

                if (data.error) {
                    document.getElementById('columnInfo').innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                searchValues = data.values;

                // Get column type detection
                try {
                    const typeData = await MesApi.post('/api/excel-query/column-type', { column_name: column });
                    if (!typeData.error) {
                        excelColumnTypes[column] = typeData;
                    }
                } catch (e) {
                    console.warn('Could not detect column type:', e);
                }

                // Build info display
                const typeInfo = excelColumnTypes[column];
                const typeBadge = typeInfo ? `<span class="type-badge ${typeInfo.detected_type}">${typeInfo.type_label}</span>` : '';
                const warningClass = data.count > 1000 ? ' warning' : '';

                document.getElementById('columnInfo').innerHTML = `
                    <div class="info-box${warningClass}">
                        共 ${data.count} 個不重複值 ${typeBadge}
                        ${data.count > 1000 ? '（將分批查詢，每批 1000 筆）' : ''}
                    </div>
                `;

                document.getElementById('step3').classList.remove('disabled');

            } catch (error) {
                document.getElementById('columnInfo').innerHTML = `<div class="error">讀取失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        // Load available tables
        async function loadTables() {
            try {
                const data = await MesApi.get('/api/excel-query/tables', { silent: true });

                const select = document.getElementById('targetTable');
                select.innerHTML = '<option value="">-- 請選擇 --</option>';

                data.tables.forEach(table => {
                    select.innerHTML += `<option value="${escapeHtml(table.name)}">${escapeHtml(table.display_name)} (${escapeHtml(table.name)})</option>`;
                });
            } catch (error) {
                console.error('Failed to load tables:', error);
            }
        }

        // Step 3: Load table columns (using new table-metadata endpoint)
        async function loadTableColumns() {
            const tableName = document.getElementById('targetTable').value;
            if (!tableName) {
                tableColumns = [];
                tableColumnsMeta = [];
                tableMetadata = null;
                document.getElementById('tableInfo').innerHTML = '';
                document.getElementById('dateRangeSection').style.display = 'none';
                document.getElementById('performanceWarning').style.display = 'none';
                return;
            }

            document.getElementById('tableInfo').innerHTML = '<div class="loading"><div class="loading-spinner"></div><br>讀取欄位...</div>';

            try {
                const data = await MesApi.post('/api/excel-query/table-metadata', { table_name: tableName });

                if (data.error) {
                    document.getElementById('tableInfo').innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                tableColumnsMeta = data.columns || [];
                tableColumns = tableColumnsMeta.map(c => c.name);
                tableMetadata = data;

                // Show table info
                let infoHtml = `共 ${tableColumns.length} 個欄位`;
                if (data.row_count) {
                    infoHtml += ` | 約 ${data.row_count.toLocaleString()} 筆`;
                }
                if (data.time_field) {
                    infoHtml += ` | 時間欄位: ${escapeHtml(data.time_field)}`;
                }
                document.getElementById('tableInfo').innerHTML = `<div class="info-box">${infoHtml}</div>`;

                // Populate search column dropdown with type badges
                const searchSelect = document.getElementById('searchColumn');
                searchSelect.innerHTML = '<option value="">-- 請選擇 --</option>';
                tableColumnsMeta.forEach(col => {
                    const typeBadge = getTypeBadgeHtml(col.data_type);
                    searchSelect.innerHTML += `<option value="${escapeHtml(col.name)}" data-type="${escapeHtml(col.data_type || '')}">${escapeHtml(col.name)} ${typeBadge}</option>`;
                });

                // Populate return columns with type badges
                const container = document.getElementById('returnColumns');
                container.innerHTML = '';
                tableColumnsMeta.forEach(col => {
                    const typeBadge = getTypeBadgeHtml(col.data_type);
                    container.innerHTML += `
                        <label class="checkbox-item">
                            <input type="checkbox" value="${escapeHtml(col.name)}" checked>
                            ${escapeHtml(col.name)} ${typeBadge}
                        </label>
                    `;
                });

                // Setup date range section
                setupDateRangeSection(data);

                // Show performance warning if applicable
                if (data.performance_warning) {
                    document.getElementById('performanceWarning').textContent = data.performance_warning;
                    document.getElementById('performanceWarning').style.display = 'block';
                } else {
                    document.getElementById('performanceWarning').style.display = 'none';
                }

                document.getElementById('step4').classList.remove('disabled');
                document.getElementById('step5').classList.remove('disabled');

            } catch (error) {
                document.getElementById('tableInfo').innerHTML = `<div class="error">讀取失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        // Helper: Get type badge HTML
        function getTypeBadgeHtml(dataType) {
            if (!dataType || dataType === 'UNKNOWN') return '';

            const typeMap = {
                'VARCHAR2': { class: 'text', label: '文字' },
                'CHAR': { class: 'text', label: '文字' },
                'NVARCHAR2': { class: 'text', label: '文字' },
                'CLOB': { class: 'text', label: '文字' },
                'NUMBER': { class: 'number', label: '數值' },
                'FLOAT': { class: 'number', label: '數值' },
                'INTEGER': { class: 'number', label: '數值' },
                'DATE': { class: 'date', label: '日期' },
                'TIMESTAMP': { class: 'datetime', label: '日期時間' },
            };

            // Find matching type
            for (const [key, val] of Object.entries(typeMap)) {
                if (dataType.toUpperCase().includes(key)) {
                    return `<span class="type-badge ${val.class}">${val.label}</span>`;
                }
            }
            return `<span class="type-badge unknown">${escapeHtml(dataType)}</span>`;
        }

        // Setup date range section based on table metadata
        function setupDateRangeSection(metadata) {
            const section = document.getElementById('dateRangeSection');
            const dateColumnSelect = document.getElementById('dateColumn');

            // Find date/timestamp columns
            const dateColumns = tableColumnsMeta.filter(c => c.is_date);

            if (dateColumns.length === 0 && !metadata.time_field) {
                section.style.display = 'none';
                return;
            }

            section.style.display = 'block';
            dateColumnSelect.innerHTML = '<option value="">-- 不限時間 --</option>';

            // Add configured time_field first if available
            if (metadata.time_field) {
                dateColumnSelect.innerHTML += `<option value="${escapeHtml(metadata.time_field)}" selected>${escapeHtml(metadata.time_field)} (預設)</option>`;
            }

            // Add other date columns
            dateColumns.forEach(col => {
                if (col.name !== metadata.time_field) {
                    dateColumnSelect.innerHTML += `<option value="${escapeHtml(col.name)}">${escapeHtml(col.name)}</option>`;
                }
            });
        }

        // Set default date range (last 90 days)
        function setDefaultDateRange() {
            const today = new Date();
            const past = new Date();
            past.setDate(today.getDate() - 90);

            document.getElementById('dateFrom').value = past.toISOString().split('T')[0];
            document.getElementById('dateTo').value = today.toISOString().split('T')[0];
        }

        // Toggle advanced panel
        function toggleAdvancedPanel() {
            const panel = document.getElementById('advancedPanel');
            panel.classList.toggle('collapsed');
        }

        // Handle query type change
        function onQueryTypeChange() {
            const queryType = document.getElementById('queryType').value;
            const warningDiv = document.getElementById('performanceWarning');

            // Show warning for LIKE contains on large tables
            if (queryType === 'like_contains' && tableMetadata && tableMetadata.row_count > 10000000) {
                warningDiv.textContent = '此資料表超過 1000 萬筆，包含查詢可能較慢，建議配合日期範圍縮小查詢範圍';
                warningDiv.style.display = 'block';
            } else if (tableMetadata && tableMetadata.performance_warning && queryType === 'like_contains') {
                warningDiv.textContent = tableMetadata.performance_warning;
                warningDiv.style.display = 'block';
            } else {
                warningDiv.style.display = 'none';
            }
        }

        // Check for type mismatch between Excel column and Oracle column
        function checkTypeMismatch() {
            const warningDiv = document.getElementById('typeMismatchWarning');
            const searchCol = document.getElementById('searchColumn').value;
            const excelCol = document.getElementById('excelColumn').value;

            if (!searchCol || !excelCol) {
                warningDiv.innerHTML = '';
                return;
            }

            // Get types
            const oracleMeta = tableColumnsMeta.find(c => c.name === searchCol);
            const excelType = excelColumnTypes[excelCol];

            if (!oracleMeta || !excelType) {
                warningDiv.innerHTML = '';
                return;
            }

            // Check for potential mismatches
            let warning = '';
            if (oracleMeta.is_number && excelType.detected_type === 'text') {
                warning = '欄位類型可能不相符：Excel 欄位為文字，Oracle 欄位為數值';
            } else if (oracleMeta.is_date && excelType.detected_type !== 'date' && excelType.detected_type !== 'datetime') {
                warning = '欄位類型可能不相符：Oracle 欄位為日期類型';
            }

            if (warning) {
                warningDiv.innerHTML = `<div class="type-mismatch-warning">${warning}</div>`;
            } else {
                warningDiv.innerHTML = '';
            }
        }

        function selectAllColumns() {
            document.querySelectorAll('#returnColumns input[type="checkbox"]').forEach(cb => cb.checked = true);
        }

        function deselectAllColumns() {
            document.querySelectorAll('#returnColumns input[type="checkbox"]').forEach(cb => cb.checked = false);
        }

        function getSelectedReturnColumns() {
            const checkboxes = document.querySelectorAll('#returnColumns input[type="checkbox"]:checked');
            return Array.from(checkboxes).map(cb => cb.value);
        }

        function getQueryParams() {
            const params = {
                table_name: document.getElementById('targetTable').value,
                search_column: document.getElementById('searchColumn').value,
                return_columns: getSelectedReturnColumns(),
                search_values: searchValues,
                query_type: document.getElementById('queryType').value
            };

            // Add date range if specified
            const dateColumn = document.getElementById('dateColumn').value;
            const dateFrom = document.getElementById('dateFrom').value;
            const dateTo = document.getElementById('dateTo').value;

            if (dateColumn) {
                params.date_column = dateColumn;
                if (dateFrom) params.date_from = dateFrom;
                if (dateTo) params.date_to = dateTo;
            }

            return params;
        }

        function validateQuery() {
            const params = getQueryParams();

            if (!params.table_name) {
                alert('請選擇資料表');
                return false;
            }
            if (!params.search_column) {
                alert('請選擇查詢欄位');
                return false;
            }
            if (params.return_columns.length === 0) {
                alert('請至少選擇一個回傳欄位');
                return false;
            }
            if (params.search_values.length === 0) {
                alert('無查詢值，請先選擇 Excel 欄位');
                return false;
            }

            // Validate LIKE keyword limit
            if (params.query_type.startsWith('like_') && params.search_values.length > 100) {
                alert('LIKE 查詢最多支援 100 個關鍵字，目前有 ' + params.search_values.length + ' 個');
                return false;
            }

            // Validate date range
            if (params.date_from && params.date_to) {
                const from = new Date(params.date_from);
                const to = new Date(params.date_to);
                if (from > to) {
                    alert('起始日期不可晚於結束日期');
                    document.getElementById('dateRangeError').textContent = '起始日期不可晚於結束日期';
                    document.getElementById('dateRangeError').style.display = 'block';
                    return false;
                }
                const daysDiff = (to - from) / (1000 * 60 * 60 * 24);
                if (daysDiff > 365) {
                    alert('日期範圍不可超過 365 天');
                    document.getElementById('dateRangeError').textContent = '日期範圍不可超過 365 天';
                    document.getElementById('dateRangeError').style.display = 'block';
                    return false;
                }
                document.getElementById('dateRangeError').style.display = 'none';
            }

            return true;
        }

        // Step 5: Execute query
        async function executeQuery() {
            if (!validateQuery()) return;

            const params = getQueryParams();
            const isAdvanced = params.query_type !== 'in' || params.date_column;
            const batchCount = params.query_type === 'in' ? Math.ceil(params.search_values.length / 1000) : 1;

            // Build loading message
            let loadingMsg = `查詢中... (${params.search_values.length} 筆`;
            if (params.query_type !== 'in') {
                const typeLabels = {
                    'like_contains': '包含查詢',
                    'like_prefix': '前綴查詢',
                    'like_suffix': '後綴查詢'
                };
                loadingMsg += `，${typeLabels[params.query_type] || params.query_type}`;
            } else if (batchCount > 1) {
                loadingMsg += `，${batchCount} 批次`;
            }
            if (params.date_from || params.date_to) {
                loadingMsg += `，日期篩選`;
            }
            loadingMsg += ')';

            document.getElementById('executeInfo').innerHTML = `
                <div class="loading">
                    <div class="loading-spinner"></div><br>
                    ${loadingMsg}
                </div>
            `;
            document.getElementById('resultSection').classList.remove('active');

            try {
                // Use advanced endpoint if using advanced features
                const endpoint = isAdvanced ? '/api/excel-query/execute-advanced' : '/api/excel-query/execute';
                const data = await MesApi.post(endpoint, params);

                if (data.error) {
                    document.getElementById('executeInfo').innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                queryResult = data;

                // Build result message
                let resultMsg = `查詢完成！搜尋 ${data.search_count} 筆，找到 ${data.row_count} 筆結果`;
                if (data.query_type && data.query_type !== 'in') {
                    resultMsg += ` (${data.query_type})`;
                }

                document.getElementById('executeInfo').innerHTML = `
                    <div class="info-box">${resultMsg}</div>
                `;

                renderResult(data);

            } catch (error) {
                document.getElementById('executeInfo').innerHTML = `<div class="error">查詢失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        function renderResult(data) {
            const section = document.getElementById('resultSection');
            const statsDiv = document.getElementById('resultStats');
            const tableDiv = document.getElementById('resultTable');

            statsDiv.innerHTML = `
                <span>搜尋值: ${data.search_count}</span>
                <span>結果: ${data.row_count} 筆</span>
                ${data.batch_count > 1 ? `<span>批次: ${data.batch_count}</span>` : ''}
            `;

            if (data.data.length === 0) {
                tableDiv.innerHTML = '<div style="padding: var(--spacing-token-p40); text-align: center; color: var(--color-token-h999999);">查無資料</div>';
            } else {
                let html = '<table><thead><tr>';
                data.columns.forEach(col => {
                    html += `<th>${escapeHtml(col)}</th>`;
                });
                html += '</tr></thead><tbody>';

                const previewData = data.data.slice(0, 1000);
                previewData.forEach(row => {
                    html += '<tr>';
                    data.columns.forEach(col => {
                        if (row[col] === null || row[col] === undefined) {
                            html += '<td><i style="color:var(--color-token-h999999)">NULL</i></td>';
                        } else {
                            html += `<td>${escapeHtml(safeText(row[col]))}</td>`;
                        }
                    });
                    html += '</tr>';
                });
                html += '</tbody></table>';

                if (data.data.length > 1000) {
                    html += `<div style="padding: var(--spacing-token-p15); text-align: center; color: var(--color-token-h666666); background: var(--color-token-hf8f9fa);">
                        顯示前 1000 筆，完整資料請匯出 CSV
                    </div>`;
                }

                tableDiv.innerHTML = html;
            }

            section.classList.add('active');
            section.scrollIntoView({ behavior: 'smooth' });
        }

        // Export CSV
        async function exportCSV() {
            if (!validateQuery()) return;

            const params = getQueryParams();
            const batchCount = Math.ceil(params.search_values.length / 1000);

            document.getElementById('executeInfo').innerHTML = `
                <div class="loading">
                    <div class="loading-spinner"></div><br>
                    匯出中... (${params.search_values.length} 筆，${batchCount} 批次)
                </div>
            `;

            try {
                // Note: CSV export uses native fetch for blob response
                const response = await fetch('/api/excel-query/export-csv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });

                if (!response.ok) {
                    const data = await response.json();
                    document.getElementById('executeInfo').innerHTML = `<div class="error">${escapeHtml(data.error || '匯出失敗')}</div>`;
                    return;
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'query_result.csv';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                document.getElementById('executeInfo').innerHTML = `
                    <div class="info-box">CSV 匯出完成！</div>
                `;

            } catch (error) {
                document.getElementById('executeInfo').innerHTML = `<div class="error">匯出失敗: ${escapeHtml(error.message)}</div>`;
            }
        }
    

Object.assign(window, {
uploadExcel,
renderPreviewTable,
loadColumnValues,
loadTables,
loadTableColumns,
getTypeBadgeHtml,
setupDateRangeSection,
setDefaultDateRange,
toggleAdvancedPanel,
onQueryTypeChange,
checkTypeMismatch,
selectAllColumns,
deselectAllColumns,
getSelectedReturnColumns,
getQueryParams,
validateQuery,
executeQuery,
renderResult,
exportCSV,
});
