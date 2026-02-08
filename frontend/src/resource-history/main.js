import { ensureMesApiAvailable } from '../core/api.js';
import { getPageContract } from '../core/field-contracts.js';
import { buildResourceKpiFromHours } from '../core/compute.js';
import { groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();
window.__MES_FRONTEND_CORE__ = { buildResourceKpiFromHours, groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText };
window.__FIELD_CONTRACTS__ = window.__FIELD_CONTRACTS__ || {};
window.__FIELD_CONTRACTS__['resource_history:detail_table'] = getPageContract('resource_history', 'detail_table');
window.__FIELD_CONTRACTS__['resource_history:kpi'] = getPageContract('resource_history', 'kpi');

const detailTableFields = getPageContract('resource_history', 'detail_table');


(function() {
    // ============================================================
    // State
    // ============================================================
    let currentGranularity = 'day';
    let summaryData = null;
    let detailData = null;
    let hierarchyState = {};  // Track expanded/collapsed state
    let charts = {};

    // ============================================================
    // DOM Elements
    // ============================================================
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const workcenterGroupsTrigger = document.getElementById('workcenterGroupsTrigger');
    const workcenterGroupsDropdown = document.getElementById('workcenterGroupsDropdown');
    const workcenterGroupsOptions = document.getElementById('workcenterGroupsOptions');
    const familiesTrigger = document.getElementById('familiesTrigger');
    const familiesDropdown = document.getElementById('familiesDropdown');
    const familiesOptions = document.getElementById('familiesOptions');
    const isProductionCheckbox = document.getElementById('isProduction');
    const isKeyCheckbox = document.getElementById('isKey');
    const isMonitorCheckbox = document.getElementById('isMonitor');
    const queryBtn = document.getElementById('queryBtn');
    const exportBtn = document.getElementById('exportBtn');
    const expandAllBtn = document.getElementById('expandAllBtn');
    const collapseAllBtn = document.getElementById('collapseAllBtn');
    const loadingOverlay = document.getElementById('loadingOverlay');

    // Selected values for multi-select
    let selectedWorkcenterGroups = [];
    let selectedFamilies = [];

    // ============================================================
    // Initialization
    // ============================================================
    function init() {
        setDefaultDates();
        applyDetailTableHeaders();
        loadFilterOptions();
        setupEventListeners();
        initCharts();
    }

    function setDefaultDates() {
        const today = new Date();
        const endDate = new Date(today);
        endDate.setDate(endDate.getDate() - 1);  // Yesterday
        const startDate = new Date(endDate);
        startDate.setDate(startDate.getDate() - 6);  // 7 days ago

        startDateInput.value = formatDate(startDate);
        endDateInput.value = formatDate(endDate);
    }

    function formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    function setupEventListeners() {
        // Granularity buttons
        document.querySelectorAll('.granularity-btns button').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.granularity-btns button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentGranularity = btn.dataset.granularity;
            });
        });

        // Query button
        queryBtn.addEventListener('click', executeQuery);

        // Export button
        exportBtn.addEventListener('click', exportCsv);

        // Expand/Collapse buttons
        expandAllBtn.addEventListener('click', () => toggleAllRows(true));
        collapseAllBtn.addEventListener('click', () => toggleAllRows(false));
    }

    function applyDetailTableHeaders() {
        const headers = document.querySelectorAll('.detail-table thead th');
        if (!headers || headers.length < 10) return;

        const byKey = {};
        detailTableFields.forEach((field) => {
            byKey[field.api_key] = field.ui_label;
        });

        headers[1].textContent = byKey.ou_pct || headers[1].textContent;
        headers[2].textContent = byKey.availability_pct || headers[2].textContent;
        headers[3].textContent = byKey.prd_hours ? byKey.prd_hours.replace('(h)', '') : headers[3].textContent;
        headers[4].textContent = byKey.sby_hours ? byKey.sby_hours.replace('(h)', '') : headers[4].textContent;
        headers[5].textContent = byKey.udt_hours ? byKey.udt_hours.replace('(h)', '') : headers[5].textContent;
        headers[6].textContent = byKey.sdt_hours ? byKey.sdt_hours.replace('(h)', '') : headers[6].textContent;
        headers[7].textContent = byKey.egt_hours ? byKey.egt_hours.replace('(h)', '') : headers[7].textContent;
        headers[8].textContent = byKey.nst_hours ? byKey.nst_hours.replace('(h)', '') : headers[8].textContent;
    }

    function initCharts() {
        charts.trend = echarts.init(document.getElementById('trendChart'));
        charts.stacked = echarts.init(document.getElementById('stackedChart'));
        charts.comparison = echarts.init(document.getElementById('comparisonChart'));
        charts.heatmap = echarts.init(document.getElementById('heatmapChart'));

        // Handle window resize
        window.addEventListener('resize', () => {
            Object.values(charts).forEach(chart => chart.resize());
        });
    }

    // ============================================================
    // API Calls (using MesApi client with timeout and retry)
    // ============================================================
    const API_TIMEOUT = 60000;  // 60 seconds timeout

    async function loadFilterOptions() {
        try {
            const result = await MesApi.get('/api/resource/history/options', {
                timeout: API_TIMEOUT,
                silent: true  // Don't show toast for filter options
            });
            if (result.success) {
                populateMultiSelect(workcenterGroupsOptions, result.data.workcenter_groups, 'workcenter');
                populateMultiSelect(familiesOptions, result.data.families.map(f => ({name: f})), 'family');
                setupMultiSelectDropdowns();
            }
        } catch (error) {
            console.error('Failed to load filter options:', error);
        }
    }

    function populateMultiSelect(container, options, type) {
        container.innerHTML = '';
        options.forEach(opt => {
            const name = opt.name || opt;
            const div = document.createElement('div');
            div.className = 'multi-select-option';
            div.innerHTML = `
                <input type="checkbox" value="${name}" data-type="${type}">
                <span>${name}</span>
            `;
            div.querySelector('input').addEventListener('change', (e) => {
                if (type === 'workcenter') {
                    updateSelectedWorkcenterGroups();
                } else {
                    updateSelectedFamilies();
                }
            });
            container.appendChild(div);
        });
    }

    function setupMultiSelectDropdowns() {
        // Workcenter Groups dropdown toggle
        workcenterGroupsTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            workcenterGroupsDropdown.classList.toggle('show');
            familiesDropdown.classList.remove('show');
        });

        // Families dropdown toggle
        familiesTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            familiesDropdown.classList.toggle('show');
            workcenterGroupsDropdown.classList.remove('show');
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', () => {
            workcenterGroupsDropdown.classList.remove('show');
            familiesDropdown.classList.remove('show');
        });

        // Prevent dropdown close when clicking inside
        workcenterGroupsDropdown.addEventListener('click', (e) => e.stopPropagation());
        familiesDropdown.addEventListener('click', (e) => e.stopPropagation());
    }

    function updateSelectedWorkcenterGroups() {
        const checkboxes = workcenterGroupsOptions.querySelectorAll('input[type="checkbox"]:checked');
        selectedWorkcenterGroups = Array.from(checkboxes).map(cb => cb.value);
        updateMultiSelectText(workcenterGroupsTrigger, selectedWorkcenterGroups, '全部站點');
    }

    function updateSelectedFamilies() {
        const checkboxes = familiesOptions.querySelectorAll('input[type="checkbox"]:checked');
        selectedFamilies = Array.from(checkboxes).map(cb => cb.value);
        updateMultiSelectText(familiesTrigger, selectedFamilies, '全部型號');
    }

    function updateMultiSelectText(trigger, selected, defaultText) {
        const textSpan = trigger.querySelector('.multi-select-text');
        if (selected.length === 0) {
            textSpan.textContent = defaultText;
        } else if (selected.length === 1) {
            textSpan.textContent = selected[0];
        } else {
            textSpan.textContent = `已選 ${selected.length} 項`;
        }
    }

    // Global functions for select all / clear all
    window.selectAllWorkcenterGroups = function() {
        workcenterGroupsOptions.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
        updateSelectedWorkcenterGroups();
    };

    window.clearAllWorkcenterGroups = function() {
        workcenterGroupsOptions.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
        updateSelectedWorkcenterGroups();
    };

    window.selectAllFamilies = function() {
        familiesOptions.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
        updateSelectedFamilies();
    };

    window.clearAllFamilies = function() {
        familiesOptions.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
        updateSelectedFamilies();
    };

    function buildQueryString() {
        const params = new URLSearchParams();
        params.append('start_date', startDateInput.value);
        params.append('end_date', endDateInput.value);
        params.append('granularity', currentGranularity);

        // Add multi-select params
        selectedWorkcenterGroups.forEach(g => params.append('workcenter_groups', g));
        selectedFamilies.forEach(f => params.append('families', f));

        if (isProductionCheckbox.checked) params.append('is_production', '1');
        if (isKeyCheckbox.checked) params.append('is_key', '1');
        if (isMonitorCheckbox.checked) params.append('is_monitor', '1');

        return params.toString();
    }

    async function executeQuery() {
        // Validate date range
        const startDate = new Date(startDateInput.value);
        const endDate = new Date(endDateInput.value);
        const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);

        if (diffDays > 730) {
            Toast.warning('查詢範圍不可超過兩年');
            return;
        }

        if (diffDays < 0) {
            Toast.warning('結束日期必須大於起始日期');
            return;
        }

        showLoading();
        queryBtn.disabled = true;

        try {
            const queryString = buildQueryString();
            const summaryUrl = `/api/resource/history/summary?${queryString}`;
            const detailUrl = `/api/resource/history/detail?${queryString}`;

            // Fetch summary and detail in parallel using MesApi
            const [summaryResult, detailResult] = await Promise.all([
                MesApi.get(summaryUrl, { timeout: API_TIMEOUT }),
                MesApi.get(detailUrl, { timeout: API_TIMEOUT })
            ]);

            if (summaryResult.success) {
                const rawSummary = summaryResult.data || {};
                const computedKpi = mergeComputedKpi(rawSummary.kpi || {});
                const computedTrend = (rawSummary.trend || []).map((trendPoint) => mergeComputedKpi(trendPoint));
                summaryData = {
                    ...rawSummary,
                    kpi: computedKpi,
                    trend: computedTrend
                };

                updateKpiCards(summaryData.kpi);
                updateTrendChart(summaryData.trend);
                updateStackedChart(summaryData.trend);
                updateComparisonChart(summaryData.workcenter_comparison);
                updateHeatmapChart(summaryData.heatmap);
            } else {
                Toast.error(summaryResult.error || '查詢摘要失敗');
            }

            if (detailResult.success) {
                detailData = detailResult.data;
                hierarchyState = {};
                renderDetailTable(detailData);

                // Show warning if data was truncated
                if (detailResult.truncated) {
                    Toast.warning(`明細資料超過 ${detailResult.max_records} 筆，僅顯示前 ${detailResult.max_records} 筆。請使用篩選條件縮小範圍。`);
                }
            } else {
                Toast.error(detailResult.error || '查詢明細失敗');
            }

        } catch (error) {
            console.error('Query failed:', error);
            Toast.error('查詢失敗: ' + error.message);
        } finally {
            hideLoading();
            queryBtn.disabled = false;
        }
    }

    // ============================================================
    // KPI Cards
    // ============================================================
    function mergeComputedKpi(kpi) {
        return {
            ...kpi,
            ...buildResourceKpiFromHours(kpi)
        };
    }

    function updateKpiCards(kpi) {
        // OU% and AVAIL%
        document.getElementById('kpiOuPct').textContent = kpi.ou_pct + '%';
        document.getElementById('kpiAvailabilityPct').textContent = kpi.availability_pct + '%';

        // PRD
        document.getElementById('kpiPrdHours').textContent = formatHours(kpi.prd_hours);
        document.getElementById('kpiPrdPct').textContent = `生產 (${kpi.prd_pct || 0}%)`;

        // SBY
        document.getElementById('kpiSbyHours').textContent = formatHours(kpi.sby_hours);
        document.getElementById('kpiSbyPct').textContent = `待機 (${kpi.sby_pct || 0}%)`;

        // UDT
        document.getElementById('kpiUdtHours').textContent = formatHours(kpi.udt_hours);
        document.getElementById('kpiUdtPct').textContent = `非計畫停機 (${kpi.udt_pct || 0}%)`;

        // SDT
        document.getElementById('kpiSdtHours').textContent = formatHours(kpi.sdt_hours);
        document.getElementById('kpiSdtPct').textContent = `計畫停機 (${kpi.sdt_pct || 0}%)`;

        // EGT
        document.getElementById('kpiEgtHours').textContent = formatHours(kpi.egt_hours);
        document.getElementById('kpiEgtPct').textContent = `工程 (${kpi.egt_pct || 0}%)`;

        // NST
        document.getElementById('kpiNstHours').textContent = formatHours(kpi.nst_hours);
        document.getElementById('kpiNstPct').textContent = `未排程 (${kpi.nst_pct || 0}%)`;

        // Machine count
        const machineCount = Number(kpi.machine_count || 0);
        document.getElementById('kpiMachineCount').textContent = machineCount.toLocaleString();
    }

    function formatHours(hours) {
        if (hours >= 1000) {
            return (hours / 1000).toFixed(1) + 'K';
        }
        return hours.toLocaleString();
    }

    // ============================================================
    // Charts
    // ============================================================
    function updateTrendChart(trend) {
        const dates = trend.map(t => t.date);
        const ouPcts = trend.map(t => t.ou_pct);
        const availabilityPcts = trend.map(t => t.availability_pct);

        charts.trend.setOption({
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    const d = trend[params[0].dataIndex];
                    return `${d.date}<br/>
                        <span style="color:#3B82F6">●</span> OU%: <b>${d.ou_pct}%</b><br/>
                        <span style="color:#10B981">●</span> AVAIL%: <b>${d.availability_pct}%</b><br/>
                        PRD: ${d.prd_hours}h<br/>
                        SBY: ${d.sby_hours}h<br/>
                        UDT: ${d.udt_hours}h`;
                }
            },
            legend: {
                data: ['OU%', 'AVAIL%'],
                bottom: 0,
                textStyle: { fontSize: 11 }
            },
            xAxis: {
                type: 'category',
                data: dates,
                axisLabel: { fontSize: 11 }
            },
            yAxis: {
                type: 'value',
                name: '%',
                max: 100,
                axisLabel: { formatter: '{value}%' }
            },
            series: [
                {
                    name: 'OU%',
                    data: ouPcts,
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.2 },
                    itemStyle: { color: '#3B82F6' },
                    lineStyle: { width: 2 }
                },
                {
                    name: 'AVAIL%',
                    data: availabilityPcts,
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.2 },
                    itemStyle: { color: '#10B981' },
                    lineStyle: { width: 2 }
                }
            ],
            grid: { left: 50, right: 20, top: 30, bottom: 50 }
        });
    }

    function updateStackedChart(trend) {
        const dates = trend.map(t => t.date);

        charts.stacked.setOption({
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function(params) {
                    const idx = params[0].dataIndex;
                    const d = trend[idx];
                    const total = d.prd_hours + d.sby_hours + d.udt_hours + d.sdt_hours + d.egt_hours + d.nst_hours;
                    const pct = (v) => total > 0 ? (v / total * 100).toFixed(1) : 0;
                    return `<b>${d.date}</b><br/>
                        <span style="color:#22c55e">●</span> PRD: ${d.prd_hours}h (${pct(d.prd_hours)}%)<br/>
                        <span style="color:#3b82f6">●</span> SBY: ${d.sby_hours}h (${pct(d.sby_hours)}%)<br/>
                        <span style="color:#ef4444">●</span> UDT: ${d.udt_hours}h (${pct(d.udt_hours)}%)<br/>
                        <span style="color:#f59e0b">●</span> SDT: ${d.sdt_hours}h (${pct(d.sdt_hours)}%)<br/>
                        <span style="color:#8b5cf6">●</span> EGT: ${d.egt_hours}h (${pct(d.egt_hours)}%)<br/>
                        <span style="color:#64748b">●</span> NST: ${d.nst_hours}h (${pct(d.nst_hours)}%)<br/>
                        <b>Total: ${total.toFixed(1)}h</b>`;
                }
            },
            legend: {
                data: ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST'],
                bottom: 0,
                textStyle: { fontSize: 10 }
            },
            xAxis: {
                type: 'category',
                data: dates,
                axisLabel: { fontSize: 10 }
            },
            yAxis: {
                type: 'value',
                name: '時數',
                axisLabel: { formatter: '{value}h' }
            },
            series: [
                { name: 'PRD', type: 'bar', stack: 'total', data: trend.map(t => t.prd_hours), itemStyle: { color: '#22c55e' } },
                { name: 'SBY', type: 'bar', stack: 'total', data: trend.map(t => t.sby_hours), itemStyle: { color: '#3b82f6' } },
                { name: 'UDT', type: 'bar', stack: 'total', data: trend.map(t => t.udt_hours), itemStyle: { color: '#ef4444' } },
                { name: 'SDT', type: 'bar', stack: 'total', data: trend.map(t => t.sdt_hours), itemStyle: { color: '#f59e0b' } },
                { name: 'EGT', type: 'bar', stack: 'total', data: trend.map(t => t.egt_hours), itemStyle: { color: '#8b5cf6' } },
                { name: 'NST', type: 'bar', stack: 'total', data: trend.map(t => t.nst_hours), itemStyle: { color: '#64748b' } }
            ],
            grid: { left: 50, right: 20, top: 30, bottom: 60 }
        });
    }

    function updateComparisonChart(comparison) {
        // Take top 15 workcenters and reverse for bottom-to-top display (highest at top)
        const data = comparison.slice(0, 15).reverse();
        const workcenters = data.map(d => d.workcenter);
        const ouPcts = data.map(d => d.ou_pct);

        charts.comparison.setOption({
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function(params) {
                    const d = data[params[0].dataIndex];
                    return `${d.workcenter}<br/>OU%: <b>${d.ou_pct}%</b><br/>機台數: ${d.machine_count}`;
                }
            },
            xAxis: {
                type: 'value',
                name: 'OU%',
                max: 100,
                axisLabel: { formatter: '{value}%' }
            },
            yAxis: {
                type: 'category',
                data: workcenters,
                axisLabel: { fontSize: 10 }
            },
            series: [{
                type: 'bar',
                data: ouPcts,
                itemStyle: {
                    color: function(params) {
                        const val = params.value;
                        if (val >= 80) return '#22c55e';
                        if (val >= 50) return '#f59e0b';
                        return '#ef4444';
                    }
                }
            }],
            grid: { left: 100, right: 30, top: 20, bottom: 30 }
        });
    }

    function updateHeatmapChart(heatmap) {
        if (!heatmap || heatmap.length === 0) {
            charts.heatmap.clear();
            return;
        }

        // Build workcenter list with sequence for sorting
        const wcSeqMap = {};
        heatmap.forEach(h => {
            wcSeqMap[h.workcenter] = h.workcenter_seq ?? 999;
        });

        // Get unique workcenters sorted by sequence ascending (smaller sequence first, e.g. 點測 before TMTT)
        const workcenters = [...new Set(heatmap.map(h => h.workcenter))]
            .sort((a, b) => wcSeqMap[a] - wcSeqMap[b]);
        const dates = [...new Set(heatmap.map(h => h.date))].sort();

        // Build data matrix
        const data = heatmap.map(h => [
            dates.indexOf(h.date),
            workcenters.indexOf(h.workcenter),
            h.ou_pct
        ]);

        charts.heatmap.setOption({
            tooltip: {
                position: 'top',
                formatter: function(params) {
                    return `${workcenters[params.value[1]]}<br/>${dates[params.value[0]]}<br/>OU%: <b>${params.value[2]}%</b>`;
                }
            },
            xAxis: {
                type: 'category',
                data: dates,
                splitArea: { show: true },
                axisLabel: { fontSize: 9, rotate: 45 }
            },
            yAxis: {
                type: 'category',
                data: workcenters,
                splitArea: { show: true },
                axisLabel: { fontSize: 9 }
            },
            visualMap: {
                min: 0,
                max: 100,
                calculable: true,
                orient: 'horizontal',
                left: 'center',
                bottom: 0,
                inRange: {
                    color: ['#ef4444', '#f59e0b', '#22c55e']
                }
            },
            series: [{
                type: 'heatmap',
                data: data,
                label: { show: false },
                emphasis: {
                    itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' }
                }
            }],
            grid: { left: 100, right: 20, top: 10, bottom: 60 }
        });
    }

    // ============================================================
    // Hierarchical Table
    // ============================================================
    function renderDetailTable(data) {
        const tbody = document.getElementById('detailTableBody');

        if (!data || data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10">
                        <div class="placeholder">
                            <div class="placeholder-icon">&#128269;</div>
                            <div class="placeholder-text">無符合條件的資料</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        // Build hierarchy
        const hierarchy = buildHierarchy(data);

        // Render rows
        tbody.innerHTML = '';
        hierarchy.forEach(wc => {
            // Workcenter level
            const wcRow = createRow(wc, 0, `wc_${wc.workcenter}`);
            tbody.appendChild(wcRow);

            // Family level
            if (hierarchyState[`wc_${wc.workcenter}`]) {
                wc.families.forEach(fam => {
                    const famRow = createRow(fam, 1, `fam_${wc.workcenter}_${fam.family}`);
                    famRow.dataset.parent = `wc_${wc.workcenter}`;
                    tbody.appendChild(famRow);

                    // Resource level
                    if (hierarchyState[`fam_${wc.workcenter}_${fam.family}`]) {
                        fam.resources.forEach(res => {
                            const resRow = createRow(res, 2);
                            resRow.dataset.parent = `fam_${wc.workcenter}_${fam.family}`;
                            tbody.appendChild(resRow);
                        });
                    }
                });
            }
        });
    }

    function buildHierarchy(data) {
        const wcMap = {};

        data.forEach(item => {
            const wc = item.workcenter;
            const fam = item.family;
            const wcSeq = item.workcenter_seq ?? 999;

            if (!wcMap[wc]) {
                wcMap[wc] = {
                    workcenter: wc,
                    name: wc,
                    sequence: wcSeq,
                    families: [],
                    familyMap: {},
                    ou_pct: 0, availability_pct: 0, prd_hours: 0, prd_pct: 0,
                    sby_hours: 0, sby_pct: 0, udt_hours: 0, udt_pct: 0,
                    sdt_hours: 0, sdt_pct: 0, egt_hours: 0, egt_pct: 0,
                    nst_hours: 0, nst_pct: 0, machine_count: 0
                };
            }

            if (!wcMap[wc].familyMap[fam]) {
                wcMap[wc].familyMap[fam] = {
                    family: fam,
                    name: fam,
                    resources: [],
                    ou_pct: 0, availability_pct: 0, prd_hours: 0, prd_pct: 0,
                    sby_hours: 0, sby_pct: 0, udt_hours: 0, udt_pct: 0,
                    sdt_hours: 0, sdt_pct: 0, egt_hours: 0, egt_pct: 0,
                    nst_hours: 0, nst_pct: 0, machine_count: 0
                };
                wcMap[wc].families.push(wcMap[wc].familyMap[fam]);
            }

            // Add resource
            wcMap[wc].familyMap[fam].resources.push({
                name: item.resource,
                ...item
            });

            // Aggregate to family
            const famObj = wcMap[wc].familyMap[fam];
            famObj.prd_hours += item.prd_hours;
            famObj.sby_hours += item.sby_hours;
            famObj.udt_hours += item.udt_hours;
            famObj.sdt_hours += item.sdt_hours;
            famObj.egt_hours += item.egt_hours;
            famObj.nst_hours += item.nst_hours;
            famObj.machine_count += 1;

            // Aggregate to workcenter
            wcMap[wc].prd_hours += item.prd_hours;
            wcMap[wc].sby_hours += item.sby_hours;
            wcMap[wc].udt_hours += item.udt_hours;
            wcMap[wc].sdt_hours += item.sdt_hours;
            wcMap[wc].egt_hours += item.egt_hours;
            wcMap[wc].nst_hours += item.nst_hours;
            wcMap[wc].machine_count += 1;
        });

        // Calculate OU% and percentages
        Object.values(wcMap).forEach(wc => {
            calcPercentages(wc);
            wc.families.forEach(fam => {
                calcPercentages(fam);
            });
        });

        // Sort by workcenter sequence ascending (smaller sequence first, e.g. 點測 before TMTT)
        return Object.values(wcMap).sort((a, b) => a.sequence - b.sequence);
    }

    function calcPercentages(obj) {
        Object.assign(obj, buildResourceKpiFromHours(obj));
    }

    function createRow(item, level, rowId) {
        const tr = document.createElement('tr');
        tr.className = `row-level-${level}`;
        if (rowId) tr.dataset.rowId = rowId;

        const indentClass = level > 0 ? `indent-${level}` : '';
        const hasChildren = level < 2 && (item.families?.length > 0 || item.resources?.length > 0);
        const isExpanded = rowId ? hierarchyState[rowId] : false;

        const expandBtn = hasChildren
            ? `<button class="expand-btn ${isExpanded ? 'expanded' : ''}" onclick="toggleRow('${rowId}')">&#9654;</button>`
            : '<span style="display:inline-block;width:24px;"></span>';

        tr.innerHTML = `
            <td class="${indentClass}">${expandBtn}${item.name}</td>
            <td><b>${item.ou_pct}%</b></td>
            <td><b>${item.availability_pct}%</b></td>
            <td class="status-prd">${formatHoursPct(item.prd_hours, item.prd_pct)}</td>
            <td class="status-sby">${formatHoursPct(item.sby_hours, item.sby_pct)}</td>
            <td class="status-udt">${formatHoursPct(item.udt_hours, item.udt_pct)}</td>
            <td class="status-sdt">${formatHoursPct(item.sdt_hours, item.sdt_pct)}</td>
            <td class="status-egt">${formatHoursPct(item.egt_hours, item.egt_pct)}</td>
            <td class="status-nst">${formatHoursPct(item.nst_hours, item.nst_pct)}</td>
            <td>${item.machine_count}</td>
        `;

        return tr;
    }

    function formatHoursPct(hours, pct) {
        return `${Math.round(hours * 10) / 10}h (${pct}%)`;
    }

    // Make toggleRow global
    window.toggleRow = function(rowId) {
        hierarchyState[rowId] = !hierarchyState[rowId];
        renderDetailTable(detailData);
    };

    function toggleAllRows(expand) {
        if (!detailData) return;

        const hierarchy = buildHierarchy(detailData);
        hierarchy.forEach(wc => {
            hierarchyState[`wc_${wc.workcenter}`] = expand;
            wc.families.forEach(fam => {
                hierarchyState[`fam_${wc.workcenter}_${fam.family}`] = expand;
            });
        });
        renderDetailTable(detailData);
    }

    // ============================================================
    // Export
    // ============================================================
    function exportCsv() {
        if (!startDateInput.value || !endDateInput.value) {
            Toast.warning('請先設定查詢條件');
            return;
        }

        const queryString = buildQueryString();
        const url = `/api/resource/history/export?${queryString}`;

        // Create download link
        const a = document.createElement('a');
        a.href = url;
        a.download = `resource_history_${startDateInput.value}_to_${endDateInput.value}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        Toast.success('CSV 匯出中...');
    }

    // ============================================================
    // Loading
    // ============================================================
    function showLoading() {
        loadingOverlay.classList.remove('hidden');
    }

    function hideLoading() {
        loadingOverlay.classList.add('hidden');
    }

    Object.assign(window, {
        init,
        setDefaultDates,
        formatDate,
        setupEventListeners,
        initCharts,
        loadFilterOptions,
        populateMultiSelect,
        setupMultiSelectDropdowns,
        updateSelectedWorkcenterGroups,
        updateSelectedFamilies,
        updateMultiSelectText,
        buildQueryString,
        executeQuery,
        updateKpiCards,
        formatHours,
        updateTrendChart,
        updateStackedChart,
        updateComparisonChart,
        updateHeatmapChart,
        renderDetailTable,
        buildHierarchy,
        calcPercentages,
        createRow,
        formatHoursPct,
        toggleAllRows,
        exportCsv,
        showLoading,
        hideLoading,
    });

    // ============================================================
    // Start
    // ============================================================
    init();
})();
