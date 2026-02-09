import { ensureMesApiAvailable } from '../core/api.js';

ensureMesApiAvailable();

(function() {
    // ============================================================
    // State
    // ============================================================
    let analysisData = null;
    let activeFilter = null; // { dimension: 'by_workflow', field: 'WORKFLOW', value: 'xxx' }
    let sortState = { column: null, asc: true };
    const charts = {};

    const CHART_CONFIG = [
        { id: 'chartWorkflow', key: 'by_workflow', field: 'WORKFLOW', title: 'WORKFLOW' },
        { id: 'chartPackage', key: 'by_package', field: 'PRODUCTLINENAME', title: 'PACKAGE' },
        { id: 'chartType', key: 'by_type', field: 'PJ_TYPE', title: 'TYPE' },
        { id: 'chartTmtt', key: 'by_tmtt_machine', field: 'TMTT_EQUIPMENTNAME', title: 'TMTT機台' },
        { id: 'chartMold', key: 'by_mold_machine', field: 'MOLD_EQUIPMENTNAME', title: 'MOLD機台' },
    ];

    // ============================================================
    // Query
    // ============================================================
    window.executeQuery = async function() {
        const startDate = document.getElementById('startDate').value;
        const endDate = document.getElementById('endDate').value;

        if (!startDate || !endDate) {
            Toast.warning('請選擇起始和結束日期');
            return;
        }

        const btn = document.getElementById('btnQuery');
        btn.disabled = true;
        const loadingId = Toast.loading('查詢中...');

        try {
            const result = await MesApi.get('/api/tmtt-defect/analysis', {
                params: { start_date: startDate, end_date: endDate },
                timeout: 120000,
            });

            Toast.dismiss(loadingId);

            if (!result || !result.success) {
                Toast.error(result?.error || '查詢失敗');
                return;
            }

            analysisData = result.data;
            activeFilter = null;
            sortState = { column: null, asc: true };

            renderAll();
            Toast.success('查詢完成');
        } catch (err) {
            Toast.dismiss(loadingId);
            Toast.error('查詢失敗: ' + (err.message || '未知錯誤'));
        } finally {
            btn.disabled = false;
        }
    };

    // ============================================================
    // Render
    // ============================================================
    function renderAll() {
        if (!analysisData) return;

        document.getElementById('emptyState').style.display = 'none';
        document.getElementById('kpiRow').style.display = '';
        document.getElementById('chartGrid').style.display = '';
        document.getElementById('detailSection').style.display = '';

        renderKpi(analysisData.kpi);
        renderCharts(analysisData.charts);
        renderDailyTrend(analysisData.daily_trend || []);
        renderDetailTable();
    }

    function renderKpi(kpi) {
        document.getElementById('kpiInput').textContent = kpi.total_input.toLocaleString('zh-TW');
        document.getElementById('kpiLots').textContent = kpi.lot_count.toLocaleString('zh-TW');
        document.getElementById('kpiPrintQty').textContent = kpi.print_defect_qty.toLocaleString('zh-TW');
        document.getElementById('kpiPrintRate').innerHTML = kpi.print_defect_rate.toFixed(4) + '<span class="kpi-unit">%</span>';
        document.getElementById('kpiLeadQty').textContent = kpi.lead_defect_qty.toLocaleString('zh-TW');
        document.getElementById('kpiLeadRate').innerHTML = kpi.lead_defect_rate.toFixed(4) + '<span class="kpi-unit">%</span>';
    }

    // ============================================================
    // Charts
    // ============================================================
    function renderCharts(chartsData) {
        CHART_CONFIG.forEach(cfg => {
            const data = chartsData[cfg.key] || [];
            renderParetoChart(cfg.id, data, cfg.key, cfg.field, cfg.title);
        });
    }

    function renderParetoChart(containerId, data, chartKey, filterField, title) {
        if (!charts[containerId]) {
            charts[containerId] = echarts.init(document.getElementById(containerId));
        }
        const chart = charts[containerId];

        if (!data || data.length === 0) {
            chart.setOption({
                title: { text: '無資料', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
                xAxis: { show: false }, yAxis: { show: false }, series: []
            });
            return;
        }

        const names = data.map(d => d.name);
        const printRates = data.map(d => d.print_defect_rate);
        const leadRates = data.map(d => d.lead_defect_rate);
        const cumPct = data.map(d => d.cumulative_pct);

        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function(params) {
                    const name = params[0].name;
                    const item = data.find(d => d.name === name);
                    if (!item) return name;
                    return `<b>${name}</b><br/>` +
                        `投入數: ${item.input_qty.toLocaleString()}<br/>` +
                        `<span style="color:${getComputedStyle(document.documentElement).getPropertyValue('--print-color')}">●</span> 印字不良: ${item.print_defect_qty} (${item.print_defect_rate.toFixed(4)}%)<br/>` +
                        `<span style="color:${getComputedStyle(document.documentElement).getPropertyValue('--lead-color')}">●</span> 腳型不良: ${item.lead_defect_qty} (${item.lead_defect_rate.toFixed(4)}%)<br/>` +
                        `累積: ${item.cumulative_pct.toFixed(1)}%`;
                }
            },
            legend: { data: ['印字不良率', '腳型不良率', '累積%'], bottom: 0, textStyle: { fontSize: 11 } },
            grid: { left: 60, right: 60, top: 30, bottom: names.length > 8 ? 100 : 60 },
            xAxis: {
                type: 'category', data: names,
                axisLabel: {
                    rotate: names.length > 8 ? 35 : 0,
                    fontSize: 11,
                    interval: 0,
                    formatter: v => v.length > 16 ? v.slice(0, 16) + '...' : v
                }
            },
            yAxis: [
                { type: 'value', name: '不良率(%)', axisLabel: { fontSize: 10 }, splitLine: { lineStyle: { type: 'dashed' } } },
                { type: 'value', name: '累積%', max: 100, axisLabel: { fontSize: 10 } }
            ],
            series: [
                {
                    name: '印字不良率', type: 'bar', stack: 'defect',
                    data: printRates,
                    itemStyle: { color: '#ef4444' },
                    barMaxWidth: 40,
                },
                {
                    name: '腳型不良率', type: 'bar', stack: 'defect',
                    data: leadRates,
                    itemStyle: { color: '#f59e0b' },
                    barMaxWidth: 40,
                },
                {
                    name: '累積%', type: 'line', yAxisIndex: 1,
                    data: cumPct,
                    itemStyle: { color: '#6366f1' },
                    lineStyle: { width: 2 },
                    symbol: 'circle', symbolSize: 6,
                }
            ]
        };

        chart.setOption(option, true);

        // Drill-down click handler
        chart.off('click');
        chart.on('click', function(params) {
            if (params.componentType === 'series' && params.name) {
                setFilter(chartKey, filterField, params.name);
            }
        });
    }

    // ============================================================
    // Daily Trend Charts
    // ============================================================
    function renderDailyTrend(trendData) {
        renderTrendChart('chartPrintTrend', trendData, 'print_defect_rate', '印字不良率', '#ef4444');
        renderTrendChart('chartLeadTrend', trendData, 'lead_defect_rate', '腳型不良率', '#f59e0b');
    }

    function renderTrendChart(containerId, data, rateKey, label, color) {
        if (!charts[containerId]) {
            charts[containerId] = echarts.init(document.getElementById(containerId));
        }
        const chart = charts[containerId];

        if (!data || data.length === 0) {
            chart.setOption({
                title: { text: '無資料', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
                xAxis: { show: false }, yAxis: { show: false }, series: []
            });
            return;
        }

        const dates = data.map(d => d.date);
        const rates = data.map(d => d[rateKey]);
        const qtys = data.map(d => d[rateKey === 'print_defect_rate' ? 'print_defect_qty' : 'lead_defect_qty']);
        const inputs = data.map(d => d.input_qty);

        const option = {
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    const idx = params[0].dataIndex;
                    const d = data[idx];
                    return `<b>${d.date}</b><br/>` +
                        `投入數: ${d.input_qty.toLocaleString()}<br/>` +
                        `<span style="color:${color}">●</span> ${label}: ${d[rateKey].toFixed(4)}%<br/>` +
                        `不良數: ${qtys[idx].toLocaleString()}`;
                }
            },
            legend: { data: [label, '投入數'], bottom: 0, textStyle: { fontSize: 11 } },
            grid: { left: 60, right: 60, top: 30, bottom: 50 },
            xAxis: {
                type: 'category', data: dates,
                axisLabel: { fontSize: 11, rotate: dates.length > 15 ? 35 : 0 }
            },
            yAxis: [
                { type: 'value', name: '不良率(%)', axisLabel: { fontSize: 10 }, splitLine: { lineStyle: { type: 'dashed' } } },
                { type: 'value', name: '投入數', axisLabel: { fontSize: 10 } }
            ],
            series: [
                {
                    name: label, type: 'line', data: rates,
                    itemStyle: { color: color },
                    lineStyle: { width: 2 },
                    symbol: 'circle', symbolSize: 4,
                    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '33' }, { offset: 1, color: color + '05' }] } },
                },
                {
                    name: '投入數', type: 'bar', yAxisIndex: 1,
                    data: inputs,
                    itemStyle: { color: '#e0e7ff' },
                    barMaxWidth: 20,
                }
            ]
        };

        chart.setOption(option, true);
    }

    // ============================================================
    // Filter / Drill-down
    // ============================================================
    function setFilter(chartKey, field, value) {
        activeFilter = { dimension: chartKey, field: field, value: value };
        renderDetailTable();
    }

    window.clearFilter = function() {
        activeFilter = null;
        renderDetailTable();
    };

    // ============================================================
    // Detail Table
    // ============================================================
    function renderDetailTable() {
        if (!analysisData) return;

        let rows = analysisData.detail;

        // Apply filter
        const filterTag = document.getElementById('filterTag');
        const btnClear = document.getElementById('btnClear');

        if (activeFilter) {
            rows = rows.filter(r => (r[activeFilter.field] || '') === activeFilter.value);
            document.getElementById('filterLabel').textContent =
                `${activeFilter.field}: ${activeFilter.value}`;
            filterTag.style.display = '';
            btnClear.style.display = '';
        } else {
            filterTag.style.display = 'none';
            btnClear.style.display = 'none';
        }

        // Apply sort
        if (sortState.column) {
            const col = sortState.column;
            const asc = sortState.asc;
            rows = [...rows].sort((a, b) => {
                const va = a[col] ?? '';
                const vb = b[col] ?? '';
                if (typeof va === 'number' && typeof vb === 'number') {
                    return asc ? va - vb : vb - va;
                }
                return asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
            });
        }

        document.getElementById('detailCount').textContent = `(${rows.length} 筆)`;

        const tbody = document.getElementById('detailBody');
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:20px;color:#999;">無資料</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map(r => `<tr>
            <td>${r.CONTAINERNAME || ''}</td>
            <td>${r.PJ_TYPE || ''}</td>
            <td>${r.PRODUCTLINENAME || ''}</td>
            <td>${r.WORKFLOW || ''}</td>
            <td>${r.FINISHEDRUNCARD || ''}</td>
            <td>${r.TMTT_EQUIPMENTNAME || ''}</td>
            <td>${r.MOLD_EQUIPMENTNAME || ''}</td>
            <td style="text-align:right">${(r.INPUT_QTY || 0).toLocaleString()}</td>
            <td style="text-align:right;color:var(--print-color)">${r.PRINT_DEFECT_QTY || 0}</td>
            <td style="text-align:right;color:var(--print-color)">${(r.PRINT_DEFECT_RATE || 0).toFixed(4)}</td>
            <td style="text-align:right;color:var(--lead-color)">${r.LEAD_DEFECT_QTY || 0}</td>
            <td style="text-align:right;color:var(--lead-color)">${(r.LEAD_DEFECT_RATE || 0).toFixed(4)}</td>
        </tr>`).join('');

        // Update sort indicators
        document.querySelectorAll('.sort-indicator').forEach(el => el.textContent = '');
        if (sortState.column) {
            const ind = document.getElementById('sort_' + sortState.column);
            if (ind) ind.textContent = sortState.asc ? '▲' : '▼';
        }
    }

    window.sortTable = function(column) {
        if (sortState.column === column) {
            sortState.asc = !sortState.asc;
        } else {
            sortState.column = column;
            sortState.asc = true;
        }
        renderDetailTable();
    };

    // ============================================================
    // CSV Export
    // ============================================================
    window.exportCsv = function() {
        const startDate = document.getElementById('startDate').value;
        const endDate = document.getElementById('endDate').value;
        if (!startDate || !endDate) {
            Toast.warning('請先查詢資料');
            return;
        }
        window.open(`/api/tmtt-defect/export?start_date=${startDate}&end_date=${endDate}`, '_blank');
    };

    // ============================================================
    // Resize
    // ============================================================
    window.addEventListener('resize', function() {
        Object.values(charts).forEach(c => c.resize());
    });
})();
