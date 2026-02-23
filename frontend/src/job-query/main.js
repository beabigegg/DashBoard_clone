import { ensureMesApiAvailable } from '../core/api.js';
import { getPageContract } from '../core/field-contracts.js';
import { escapeHtml, groupBy, sortBy, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();
window.__MES_FRONTEND_CORE__ = { groupBy, sortBy, escapeHtml, safeText };
window.__FIELD_CONTRACTS__ = window.__FIELD_CONTRACTS__ || {};
window.__FIELD_CONTRACTS__['job_query:jobs_table'] = getPageContract('job_query', 'jobs_table');
window.__FIELD_CONTRACTS__['job_query:txn_table'] = getPageContract('job_query', 'txn_table');

const jobTableFields = getPageContract('job_query', 'jobs_table');
const txnTableFields = getPageContract('job_query', 'txn_table');

function toDataToken(value) {
  return encodeURIComponent(safeText(value));
}

function fromDataToken(value) {
  if (!value) {
    return '';
  }
  try {
    return decodeURIComponent(value);
  } catch (_error) {
    return value;
  }
}

function renderJobCell(job, apiKey) {
  if (apiKey === 'JOBSTATUS') {
    const value = safeText(job[apiKey]);
    const classToken = safeText(value).replace(/[^A-Za-z0-9_-]/g, '_');
    const escaped = escapeHtml(value);
    return `<span class="status-badge ${classToken}">${escaped}</span>`;
  }
  if (apiKey === 'CREATEDATE' || apiKey === 'COMPLETEDATE') {
    return formatDate(job[apiKey]);
  }
  return escapeHtml(safeText(job[apiKey]));
}

function renderTxnCell(txn, apiKey) {
  if (apiKey === 'FROMJOBSTATUS' || apiKey === 'JOBSTATUS') {
    const value = safeText(txn[apiKey], '-');
    const classToken = safeText(value).replace(/[^A-Za-z0-9_-]/g, '_');
    const escaped = escapeHtml(value);
    return `<span class="status-badge ${classToken}">${escaped}</span>`;
  }
  if (apiKey === 'TXNDATE') {
    return formatDate(txn[apiKey]);
  }
  if (apiKey === 'USER_NAME') {
    return escapeHtml(safeText(txn.USER_NAME || txn.EMP_NAME));
  }
  return escapeHtml(safeText(txn[apiKey]));
}


        // State
        let allEquipments = [];
        let selectedEquipments = new Set();
        let jobsData = [];
        let expandedJobs = new Set();

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadEquipments();
            setLast90Days();

            const equipmentList = document.getElementById('equipmentList');
            if (equipmentList) {
                equipmentList.addEventListener('click', handleEquipmentListClick);
            }

            const resultSection = document.getElementById('resultSection');
            if (resultSection) {
                resultSection.addEventListener('click', handleResultSectionClick);
            }

            // Close dropdown when clicking outside
            document.addEventListener('click', (e) => {
                const dropdown = document.getElementById('equipmentDropdown');
                const selector = document.querySelector('.equipment-selector');
                if (!selector.contains(e.target)) {
                    dropdown.classList.remove('show');
                }
            });
        });

        // Load equipments from cache
        async function loadEquipments() {
            try {
                const data = await MesApi.get('/api/job-query/resources');
                if (data.error) {
                    document.getElementById('equipmentList').innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                allEquipments = data.data;
                renderEquipmentList(allEquipments);
            } catch (error) {
                document.getElementById('equipmentList').innerHTML = `<div class="error">載入失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        // Render equipment list
        function renderEquipmentList(equipments) {
            const container = document.getElementById('equipmentList');

            if (!equipments || equipments.length === 0) {
                container.innerHTML = '<div class="empty-state">無設備資料</div>';
                return;
            }

            let html = '';
            const grouped = groupBy(equipments, (eq) => safeText(eq.WORKCENTERNAME, '未分類'));
            const workcenters = sortBy(Object.keys(grouped), (name) => name);

            workcenters.forEach((workcenterName) => {
                const groupEquipments = grouped[workcenterName];
                const groupIds = groupEquipments.map((eq) => eq.RESOURCEID);
                const selectedInGroup = groupIds.filter((id) => selectedEquipments.has(id)).length;
                const allSelected = selectedInGroup === groupIds.length;
                const someSelected = selectedInGroup > 0 && !allSelected;
                const escapedName = escapeHtml(workcenterName);
                const workcenterToken = toDataToken(workcenterName);
                html += `<div class="workcenter-group-header" data-action="toggle-workcenter-group" data-workcenter="${workcenterToken}">
                    <input type="checkbox" ${allSelected ? 'checked' : ''} ${someSelected ? 'class="indeterminate"' : ''} data-action="toggle-workcenter-group" data-workcenter="${workcenterToken}">
                    <span class="workcenter-group-name">${escapedName}</span>
                    <span class="workcenter-group-count">${selectedInGroup}/${groupIds.length}</span>
                </div>`;
                groupEquipments.forEach((eq) => {
                    const isSelected = selectedEquipments.has(eq.RESOURCEID);
                    const resourceId = safeText(eq.RESOURCEID);
                    const resourceIdToken = toDataToken(resourceId);
                    const resourceName = escapeHtml(safeText(eq.RESOURCENAME));
                    const familyName = escapeHtml(safeText(eq.RESOURCEFAMILYNAME));

                    html += `
                        <div class="equipment-item ${isSelected ? 'selected' : ''}" data-action="toggle-equipment" data-resource-id="${resourceIdToken}">
                            <input type="checkbox" ${isSelected ? 'checked' : ''} data-action="toggle-equipment" data-resource-id="${resourceIdToken}">
                            <div class="equipment-info">
                                <div class="equipment-name">${resourceName}</div>
                                <div class="equipment-workcenter">${familyName}</div>
                            </div>
                        </div>
                    `;
                });
            });

            container.innerHTML = html;
        }

        function handleEquipmentListClick(event) {
            const trigger = event.target.closest('[data-action]');
            if (!trigger) {
                return;
            }

            if (trigger.dataset.action === 'toggle-workcenter-group') {
                const workcenterName = fromDataToken(trigger.dataset.workcenter);
                if (!workcenterName) {
                    return;
                }
                toggleWorkcenterGroup(workcenterName);
                return;
            }

            if (trigger.dataset.action === 'toggle-equipment') {
                const resourceId = fromDataToken(trigger.dataset.resourceId);
                if (!resourceId) {
                    return;
                }
                toggleEquipment(resourceId);
            }
        }

        // Toggle equipment dropdown
        function toggleEquipmentDropdown() {
            const dropdown = document.getElementById('equipmentDropdown');
            dropdown.classList.toggle('show');
        }

        // Filter equipments by search
        function filterEquipments(query) {
            const q = query.toLowerCase();
            const filtered = allEquipments.filter(eq =>
                (eq.RESOURCENAME && eq.RESOURCENAME.toLowerCase().includes(q)) ||
                (eq.WORKCENTERNAME && eq.WORKCENTERNAME.toLowerCase().includes(q)) ||
                (eq.RESOURCEFAMILYNAME && eq.RESOURCEFAMILYNAME.toLowerCase().includes(q))
            );
            renderEquipmentList(filtered);
        }

        // Toggle equipment selection
        function toggleEquipment(resourceId) {
            if (selectedEquipments.has(resourceId)) {
                selectedEquipments.delete(resourceId);
            } else {
                selectedEquipments.add(resourceId);
            }
            updateSelectedDisplay();
            renderEquipmentList(allEquipments.filter(eq => {
                const search = document.querySelector('.equipment-search');
                if (!search || !search.value) return true;
                const q = search.value.toLowerCase();
                return (eq.RESOURCENAME && eq.RESOURCENAME.toLowerCase().includes(q)) ||
                       (eq.WORKCENTERNAME && eq.WORKCENTERNAME.toLowerCase().includes(q));
            }));
        }

        // Toggle entire workcenter group selection
        function toggleWorkcenterGroup(workcenterName) {
            const groupEquipments = allEquipments.filter(
                (eq) => safeText(eq.WORKCENTERNAME, '未分類') === workcenterName
            );
            const groupIds = groupEquipments.map((eq) => eq.RESOURCEID);
            const allSelected = groupIds.every((id) => selectedEquipments.has(id));

            if (allSelected) {
                groupIds.forEach((id) => selectedEquipments.delete(id));
            } else {
                groupIds.forEach((id) => selectedEquipments.add(id));
            }

            updateSelectedDisplay();
            renderEquipmentList(allEquipments.filter((eq) => {
                const search = document.querySelector('.equipment-search');
                if (!search || !search.value) return true;
                const q = search.value.toLowerCase();
                return (eq.RESOURCENAME && eq.RESOURCENAME.toLowerCase().includes(q)) ||
                       (eq.WORKCENTERNAME && eq.WORKCENTERNAME.toLowerCase().includes(q));
            }));
        }

        // Update selected display
        function updateSelectedDisplay() {
            const display = document.getElementById('equipmentDisplay');
            const count = document.getElementById('selectedCount');

            if (selectedEquipments.size === 0) {
                display.textContent = '點擊選擇設備...';
                count.textContent = '';
            } else if (selectedEquipments.size <= 3) {
                const names = allEquipments
                    .filter(eq => selectedEquipments.has(eq.RESOURCEID))
                    .map(eq => eq.RESOURCENAME)
                    .join(', ');
                display.textContent = names;
                count.textContent = `已選擇 ${selectedEquipments.size} 台設備`;
            } else {
                display.textContent = `已選擇 ${selectedEquipments.size} 台設備`;
                count.textContent = '';
            }
        }

        // Set last 90 days
        function setLast90Days() {
            const today = new Date();
            const past = new Date();
            past.setDate(today.getDate() - 90);

            document.getElementById('dateFrom').value = past.toISOString().split('T')[0];
            document.getElementById('dateTo').value = today.toISOString().split('T')[0];
        }

        // Validate inputs
        function validateInputs() {
            if (selectedEquipments.size === 0) {
                Toast.error('請選擇至少一台設備');
                return false;
            }

            const dateFrom = document.getElementById('dateFrom').value;
            const dateTo = document.getElementById('dateTo').value;

            if (!dateFrom || !dateTo) {
                Toast.error('請指定日期範圍');
                return false;
            }

            const from = new Date(dateFrom);
            const to = new Date(dateTo);

            if (to < from) {
                Toast.error('結束日期不可早於起始日期');
                return false;
            }

            const daysDiff = (to - from) / (1000 * 60 * 60 * 24);
            if (daysDiff > 365) {
                Toast.error('日期範圍不可超過 365 天');
                return false;
            }

            return true;
        }

        // Query jobs
        async function queryJobs() {
            if (!validateInputs()) return;

            const resultSection = document.getElementById('resultSection');
            resultSection.innerHTML = `
                <div class="loading">
                    <div class="loading-spinner"></div>
                    <br>查詢中...
                </div>
            `;

            document.getElementById('queryBtn').disabled = true;
            document.getElementById('exportBtn').disabled = true;

            try {
                const data = await MesApi.post('/api/job-query/jobs', {
                    resource_ids: Array.from(selectedEquipments),
                    start_date: document.getElementById('dateFrom').value,
                    end_date: document.getElementById('dateTo').value
                });

                if (data.error) {
                    resultSection.innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
                    return;
                }

                jobsData = data.data;
                expandedJobs.clear();
                renderJobsTable();

                document.getElementById('exportBtn').disabled = jobsData.length === 0;

            } catch (error) {
                resultSection.innerHTML = `<div class="error">查詢失敗: ${escapeHtml(error.message)}</div>`;
            } finally {
                document.getElementById('queryBtn').disabled = false;
            }
        }

        // Render jobs table
        function renderJobsTable() {
            const resultSection = document.getElementById('resultSection');
            const jobHeaders = jobTableFields.map((field) => `<th>${escapeHtml(field.ui_label)}</th>`).join('');

            if (!jobsData || jobsData.length === 0) {
                resultSection.innerHTML = `
                    <div class="empty-state">
                        <p>無符合條件的工單</p>
                    </div>
                `;
                return;
            }

            let html = `
                <div class="result-header">
                    <div class="result-info">共 ${jobsData.length} 筆工單</div>
                    <div class="result-actions">
                        <button type="button" class="btn btn-secondary btn-sm" data-action="expand-all">全部展開</button>
                        <button type="button" class="btn btn-secondary btn-sm" data-action="collapse-all">全部收合</button>
                    </div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 40px;"></th>
                                ${jobHeaders}
                            </tr>
                        </thead>
                        <tbody>
            `;

            jobsData.forEach((job, idx) => {
                const isExpanded = expandedJobs.has(job.JOBID);
                const jobIdToken = toDataToken(job.JOBID);
                const jobCells = jobTableFields
                    .map((field) => `<td>${renderJobCell(job, field.api_key)}</td>`)
                    .join('');
                html += `
                    <tr class="job-row ${isExpanded ? 'expanded' : ''}" id="job-row-${idx}">
                        <td>
                            <button type="button" class="expand-btn" data-action="toggle-job-history" data-job-id="${jobIdToken}" data-row-index="${idx}">
                                <span class="arrow-icon ${isExpanded ? 'rotated' : ''}">▶</span>
                            </button>
                        </td>
                        ${jobCells}
                    </tr>
                    <tr class="txn-history-row ${isExpanded ? 'show' : ''}" id="txn-row-${idx}">
                        <td colspan="${jobTableFields.length + 1}" class="txn-history-cell">
                            <div id="txn-content-${idx}">
                                ${isExpanded ? '<div class="loading"><div class="loading-spinner"></div></div>' : ''}
                            </div>
                        </td>
                    </tr>
                `;
            });

            html += `
                        </tbody>
                    </table>
                </div>
            `;

            resultSection.innerHTML = html;

            // Load expanded histories in batches to avoid thundering herd
            const pendingLoads = [];
            expandedJobs.forEach(jobId => {
                const idx = jobsData.findIndex(j => j.JOBID === jobId);
                if (idx >= 0) pendingLoads.push({ jobId, idx });
            });
            void loadHistoriesBatched(pendingLoads);
        }

        function handleResultSectionClick(event) {
            const trigger = event.target.closest('[data-action]');
            if (!trigger) {
                return;
            }

            const action = trigger.dataset.action;
            if (action === 'expand-all') {
                expandAll();
                return;
            }
            if (action === 'collapse-all') {
                collapseAll();
                return;
            }
            if (action === 'toggle-job-history') {
                const idx = Number.parseInt(trigger.dataset.rowIndex || '', 10);
                const jobId = fromDataToken(trigger.dataset.jobId);
                if (!Number.isInteger(idx) || !jobId) {
                    return;
                }
                void toggleJobHistory(jobId, idx);
            }
        }

        // Toggle job history
        async function toggleJobHistory(jobId, idx) {
            const txnRow = document.getElementById(`txn-row-${idx}`);
            const jobRow = document.getElementById(`job-row-${idx}`);
            const arrow = jobRow.querySelector('.arrow-icon');

            if (expandedJobs.has(jobId)) {
                expandedJobs.delete(jobId);
                txnRow.classList.remove('show');
                jobRow.classList.remove('expanded');
                arrow.classList.remove('rotated');
            } else {
                expandedJobs.add(jobId);
                txnRow.classList.add('show');
                jobRow.classList.add('expanded');
                arrow.classList.add('rotated');
                loadJobHistory(jobId, idx);
            }
        }

        // Load job history
        async function loadJobHistory(jobId, idx) {
            const container = document.getElementById(`txn-content-${idx}`);
            container.innerHTML = '<div class="loading" style="padding: 20px;"><div class="loading-spinner"></div></div>';

            try {
                const data = await MesApi.get(`/api/job-query/txn/${jobId}`);

                if (data.error) {
                    container.innerHTML = `<div class="error" style="margin: 10px 20px;">${escapeHtml(data.error)}</div>`;
                    return;
                }

                if (!data.data || data.data.length === 0) {
                    container.innerHTML = '<div style="padding: 20px; color: #666;">無交易歷史記錄</div>';
                    return;
                }

                const txnHeaders = txnTableFields.map((field) => `<th>${escapeHtml(field.ui_label)}</th>`).join('');
                let html = `
                    <table class="txn-history-table">
                        <thead>
                            <tr>
                                ${txnHeaders}
                            </tr>
                        </thead>
                        <tbody>
                `;

                data.data.forEach(txn => {
                    const txnCells = txnTableFields
                        .map((field) => `<td>${renderTxnCell(txn, field.api_key)}</td>`)
                        .join('');
                    html += `
                        <tr>
                            ${txnCells}
                        </tr>
                    `;
                });

                html += '</tbody></table>';
                container.innerHTML = html;

            } catch (error) {
                container.innerHTML = `<div class="error" style="margin: 10px 20px;">載入失敗: ${escapeHtml(error.message)}</div>`;
            }
        }

        // Load multiple job histories with concurrency limit
        const BATCH_CONCURRENCY = 5;
        async function loadHistoriesBatched(items) {
            for (let i = 0; i < items.length; i += BATCH_CONCURRENCY) {
                const batch = items.slice(i, i + BATCH_CONCURRENCY);
                await Promise.all(batch.map(({ jobId, idx }) => loadJobHistory(jobId, idx)));
            }
        }

        // Expand all
        function expandAll() {
            jobsData.forEach((job, idx) => {
                if (!expandedJobs.has(job.JOBID)) {
                    expandedJobs.add(job.JOBID);
                }
            });
            renderJobsTable();
        }

        // Collapse all
        function collapseAll() {
            expandedJobs.clear();
            renderJobsTable();
        }

        // Export CSV
        async function exportCsv() {
            if (!validateInputs()) return;

            document.getElementById('exportBtn').disabled = true;
            document.getElementById('exportBtn').textContent = '匯出中...';

            try {
                const response = await fetch('/api/job-query/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        resource_ids: Array.from(selectedEquipments),
                        start_date: document.getElementById('dateFrom').value,
                        end_date: document.getElementById('dateTo').value
                    })
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || '匯出失敗');
                }

                // Download file
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `job_history_${document.getElementById('dateFrom').value}_${document.getElementById('dateTo').value}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                Toast.success('CSV 匯出完成');

            } catch (error) {
                Toast.error('匯出失敗: ' + error.message);
            } finally {
                document.getElementById('exportBtn').disabled = false;
                document.getElementById('exportBtn').textContent = '匯出 CSV';
            }
        }

        // Format date
        function formatDate(dateStr) {
            if (!dateStr) return '';
            return dateStr.replace('T', ' ').substring(0, 19);
        }
    

Object.assign(window, {
loadEquipments,
renderEquipmentList,
toggleEquipmentDropdown,
filterEquipments,
toggleEquipment,
toggleWorkcenterGroup,
updateSelectedDisplay,
setLast90Days,
validateInputs,
queryJobs,
renderJobsTable,
toggleJobHistory,
loadJobHistory,
expandAll,
collapseAll,
exportCsv,
formatDate,
});
