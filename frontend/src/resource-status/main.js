import { ensureMesApiAvailable } from '../core/api.js';
import { getPageContract } from '../core/field-contracts.js';
import { buildResourceKpiFromHours } from '../core/compute.js';
import { groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText } from '../core/table-tree.js';

ensureMesApiAvailable();
window.__MES_FRONTEND_CORE__ = { buildResourceKpiFromHours, groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText };
window.__FIELD_CONTRACTS__ = window.__FIELD_CONTRACTS__ || {};
window.__FIELD_CONTRACTS__['resource_status:matrix_summary'] = getPageContract('resource_status', 'matrix_summary');


    let allEquipment = [];
    let workcenterGroups = [];
    let matrixFilter = null; // { workcenter_group, status }
    let matrixHierarchyState = {}; // Track expanded/collapsed state for matrix rows

    // ============================================================
    // Hierarchical Matrix Functions
    // ============================================================

    function buildMatrixHierarchy(equipment) {
        // Build hierarchy: workcenter_group -> resourcefamily -> equipment
        const groupMap = {};

        equipment.forEach(eq => {
            const group = eq.WORKCENTER_GROUP || 'UNKNOWN';
            const family = eq.RESOURCEFAMILYNAME || 'UNKNOWN';
            const status = eq.EQUIPMENTASSETSSTATUS || 'OTHER';
            const groupSeq = eq.WORKCENTER_GROUP_SEQ ?? 999;

            // Initialize group
            if (!groupMap[group]) {
                groupMap[group] = {
                    name: group,
                    sequence: groupSeq,
                    families: {},
                    counts: { total: 0, PRD: 0, SBY: 0, UDT: 0, SDT: 0, EGT: 0, NST: 0, OTHER: 0 }
                };
            }

            // Initialize family
            if (!groupMap[group].families[family]) {
                groupMap[group].families[family] = {
                    name: family,
                    equipment: [],
                    counts: { total: 0, PRD: 0, SBY: 0, UDT: 0, SDT: 0, EGT: 0, NST: 0, OTHER: 0 }
                };
            }

            // Add equipment to family
            groupMap[group].families[family].equipment.push(eq);

            // Map status to count key
            let statusKey = 'OTHER';
            if (['PRD'].includes(status)) statusKey = 'PRD';
            else if (['SBY'].includes(status)) statusKey = 'SBY';
            else if (['UDT', 'PM', 'BKD'].includes(status)) statusKey = 'UDT';
            else if (['SDT'].includes(status)) statusKey = 'SDT';
            else if (['EGT', 'ENG'].includes(status)) statusKey = 'EGT';
            else if (['NST', 'OFF'].includes(status)) statusKey = 'NST';

            // Update counts
            groupMap[group].counts.total++;
            groupMap[group].counts[statusKey]++;
            groupMap[group].families[family].counts.total++;
            groupMap[group].families[family].counts[statusKey]++;
        });

        // Convert to array structure
        // Sort groups by sequence ascending (smaller sequence first, e.g. 點測 before TMTT)
        // Sort families by total count descending
        const hierarchy = Object.values(groupMap).map(g => ({
            ...g,
            families: Object.values(g.families).sort((a, b) => b.counts.total - a.counts.total)
        })).sort((a, b) => a.sequence - b.sequence);

        return hierarchy;
    }

    function toggleMatrixRow(rowId) {
        matrixHierarchyState[rowId] = !matrixHierarchyState[rowId];
        renderMatrixHierarchy();
    }

    function toggleAllMatrixRows(expand) {
        const hierarchy = buildMatrixHierarchy(allEquipment);
        hierarchy.forEach(group => {
            matrixHierarchyState[`grp_${group.name}`] = expand;
            group.families.forEach(fam => {
                matrixHierarchyState[`fam_${group.name}_${fam.name}`] = expand;
            });
        });
        renderMatrixHierarchy();
    }

    function renderMatrixHierarchy() {
        const container = document.getElementById('matrixContainer');
        const hierarchy = buildMatrixHierarchy(allEquipment);

        if (hierarchy.length === 0) {
            container.innerHTML = '<div class="empty-state">無資料</div>';
            return;
        }

        let html = `
            <table class="matrix-table">
                <thead>
                    <tr>
                        <th>工站群組 / 型號 / 機台</th>
                        <th>總數</th>
                        <th>PRD</th>
                        <th>SBY</th>
                        <th>UDT</th>
                        <th>SDT</th>
                        <th>EGT</th>
                        <th>NST</th>
                        <th>OTHER</th>
                        <th>OU%</th>
                    </tr>
                </thead>
                <tbody>
        `;

        hierarchy.forEach(group => {
            const grpId = `grp_${group.name}`;
            const isGroupExpanded = matrixHierarchyState[grpId];
            const hasChildren = group.families.length > 0;

            // Calculate OU%
            const avail = group.counts.PRD + group.counts.SBY + group.counts.UDT + group.counts.SDT + group.counts.EGT;
            const ou = avail > 0 ? ((group.counts.PRD / avail) * 100).toFixed(1) : 0;
            const ouClass = ou >= 80 ? 'high' : (ou >= 50 ? 'medium' : 'low');

            // Group row (Level 0)
            const expandBtn = hasChildren
                ? `<button class="expand-btn ${isGroupExpanded ? 'expanded' : ''}" onclick="toggleMatrixRow('${grpId}')">▶</button>`
                : '<span class="expand-placeholder"></span>';

            // Helper to check if this cell is selected (supports all levels)
            const isSelected = (wg, st, fam = null, res = null) => {
                if (!matrixFilter) return false;
                if (matrixFilter.workcenter_group !== wg) return false;
                if (matrixFilter.status !== st) return false;
                if (fam !== null && matrixFilter.family !== fam) return false;
                if (res !== null && matrixFilter.resource !== res) return false;
                // Match level: if matrixFilter has family but we're checking group level, no match
                if (matrixFilter.family && fam === null) return false;
                if (matrixFilter.resource && res === null) return false;
                return true;
            };
            const grpName = group.name;

            html += `
                <tr class="row-level-0">
                    <td><span class="row-name">${expandBtn}${group.name}</span></td>
                    <td class="col-total">${group.counts.total}</td>
                    <td class="col-prd clickable ${group.counts.PRD === 0 ? 'zero' : ''} ${isSelected(grpName, 'PRD') ? 'selected' : ''}" data-wg="${grpName}" data-status="PRD" onclick="filterByMatrixCell('${grpName}', 'PRD')">${group.counts.PRD}</td>
                    <td class="col-sby clickable ${group.counts.SBY === 0 ? 'zero' : ''} ${isSelected(grpName, 'SBY') ? 'selected' : ''}" data-wg="${grpName}" data-status="SBY" onclick="filterByMatrixCell('${grpName}', 'SBY')">${group.counts.SBY}</td>
                    <td class="col-udt clickable ${group.counts.UDT === 0 ? 'zero' : ''} ${isSelected(grpName, 'UDT') ? 'selected' : ''}" data-wg="${grpName}" data-status="UDT" onclick="filterByMatrixCell('${grpName}', 'UDT')">${group.counts.UDT}</td>
                    <td class="col-sdt clickable ${group.counts.SDT === 0 ? 'zero' : ''} ${isSelected(grpName, 'SDT') ? 'selected' : ''}" data-wg="${grpName}" data-status="SDT" onclick="filterByMatrixCell('${grpName}', 'SDT')">${group.counts.SDT}</td>
                    <td class="col-egt clickable ${group.counts.EGT === 0 ? 'zero' : ''} ${isSelected(grpName, 'EGT') ? 'selected' : ''}" data-wg="${grpName}" data-status="EGT" onclick="filterByMatrixCell('${grpName}', 'EGT')">${group.counts.EGT}</td>
                    <td class="col-nst clickable ${group.counts.NST === 0 ? 'zero' : ''} ${isSelected(grpName, 'NST') ? 'selected' : ''}" data-wg="${grpName}" data-status="NST" onclick="filterByMatrixCell('${grpName}', 'NST')">${group.counts.NST}</td>
                    <td class="col-other clickable ${group.counts.OTHER === 0 ? 'zero' : ''} ${isSelected(grpName, 'OTHER') ? 'selected' : ''}" data-wg="${grpName}" data-status="OTHER" onclick="filterByMatrixCell('${grpName}', 'OTHER')">${group.counts.OTHER}</td>
                    <td><span class="ou-badge ${ouClass}">${ou}%</span></td>
                </tr>
            `;

            // Family rows (Level 1)
            if (isGroupExpanded) {
                group.families.forEach(fam => {
                    const famId = `fam_${group.name}_${fam.name}`;
                    const isFamExpanded = matrixHierarchyState[famId];
                    const hasEquipment = fam.equipment.length > 0;

                    const famAvail = fam.counts.PRD + fam.counts.SBY + fam.counts.UDT + fam.counts.SDT + fam.counts.EGT;
                    const famOu = famAvail > 0 ? ((fam.counts.PRD / famAvail) * 100).toFixed(1) : 0;
                    const famOuClass = famOu >= 80 ? 'high' : (famOu >= 50 ? 'medium' : 'low');

                    const famExpandBtn = hasEquipment
                        ? `<button class="expand-btn ${isFamExpanded ? 'expanded' : ''}" onclick="toggleMatrixRow('${famId}')">▶</button>`
                        : '<span class="expand-placeholder"></span>';

                    const famName = fam.name;
                    const escFamName = famName.replace(/'/g, "\\'");

                    html += `
                        <tr class="row-level-1 indent-1">
                            <td><span class="row-name">${famExpandBtn}${fam.name}</span></td>
                            <td class="col-total">${fam.counts.total}</td>
                            <td class="col-prd clickable ${fam.counts.PRD === 0 ? 'zero' : ''} ${isSelected(grpName, 'PRD', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="PRD" onclick="filterByMatrixCell('${grpName}', 'PRD', '${escFamName}')">${fam.counts.PRD}</td>
                            <td class="col-sby clickable ${fam.counts.SBY === 0 ? 'zero' : ''} ${isSelected(grpName, 'SBY', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="SBY" onclick="filterByMatrixCell('${grpName}', 'SBY', '${escFamName}')">${fam.counts.SBY}</td>
                            <td class="col-udt clickable ${fam.counts.UDT === 0 ? 'zero' : ''} ${isSelected(grpName, 'UDT', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="UDT" onclick="filterByMatrixCell('${grpName}', 'UDT', '${escFamName}')">${fam.counts.UDT}</td>
                            <td class="col-sdt clickable ${fam.counts.SDT === 0 ? 'zero' : ''} ${isSelected(grpName, 'SDT', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="SDT" onclick="filterByMatrixCell('${grpName}', 'SDT', '${escFamName}')">${fam.counts.SDT}</td>
                            <td class="col-egt clickable ${fam.counts.EGT === 0 ? 'zero' : ''} ${isSelected(grpName, 'EGT', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="EGT" onclick="filterByMatrixCell('${grpName}', 'EGT', '${escFamName}')">${fam.counts.EGT}</td>
                            <td class="col-nst clickable ${fam.counts.NST === 0 ? 'zero' : ''} ${isSelected(grpName, 'NST', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="NST" onclick="filterByMatrixCell('${grpName}', 'NST', '${escFamName}')">${fam.counts.NST}</td>
                            <td class="col-other clickable ${fam.counts.OTHER === 0 ? 'zero' : ''} ${isSelected(grpName, 'OTHER', famName) ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-status="OTHER" onclick="filterByMatrixCell('${grpName}', 'OTHER', '${escFamName}')">${fam.counts.OTHER}</td>
                            <td><span class="ou-badge ${famOuClass}">${famOu}%</span></td>
                        </tr>
                    `;

                    // Equipment rows (Level 2)
                    if (isFamExpanded) {
                        fam.equipment.forEach(eq => {
                            const status = eq.EQUIPMENTASSETSSTATUS || '--';
                            const statusCat = (eq.STATUS_CATEGORY || 'OTHER').toLowerCase();
                            const resId = eq.RESOURCEID || '';
                            const resName = eq.RESOURCENAME || eq.RESOURCEID || '--';
                            const escResId = resId.replace(/'/g, "\\'");

                            // Determine status category key for this equipment
                            let eqStatusKey = 'OTHER';
                            if (['PRD'].includes(status)) eqStatusKey = 'PRD';
                            else if (['SBY'].includes(status)) eqStatusKey = 'SBY';
                            else if (['UDT', 'PM', 'BKD'].includes(status)) eqStatusKey = 'UDT';
                            else if (['SDT'].includes(status)) eqStatusKey = 'SDT';
                            else if (['EGT', 'ENG'].includes(status)) eqStatusKey = 'EGT';
                            else if (['NST', 'OFF'].includes(status)) eqStatusKey = 'NST';

                            const isEqSelected = isSelected(grpName, eqStatusKey, famName, resId);

                            html += `
                                <tr class="row-level-2 indent-2 clickable-row ${isEqSelected ? 'selected' : ''}" data-wg="${grpName}" data-fam="${famName}" data-res="${resId}" onclick="filterByMatrixCell('${grpName}', '${eqStatusKey}', '${escFamName}', '${escResId}')">
                                    <td><span class="row-name"><span class="expand-placeholder"></span>${resName}</span></td>
                                    <td>1</td>
                                    <td class="col-prd ${status !== 'PRD' ? 'zero' : ''}">${status === 'PRD' ? '●' : '-'}</td>
                                    <td class="col-sby ${status !== 'SBY' ? 'zero' : ''}">${status === 'SBY' ? '●' : '-'}</td>
                                    <td class="col-udt ${!['UDT', 'PM', 'BKD'].includes(status) ? 'zero' : ''}">${['UDT', 'PM', 'BKD'].includes(status) ? '●' : '-'}</td>
                                    <td class="col-sdt ${status !== 'SDT' ? 'zero' : ''}">${status === 'SDT' ? '●' : '-'}</td>
                                    <td class="col-egt ${!['EGT', 'ENG'].includes(status) ? 'zero' : ''}">${['EGT', 'ENG'].includes(status) ? '●' : '-'}</td>
                                    <td class="col-nst ${!['NST', 'OFF'].includes(status) ? 'zero' : ''}">${['NST', 'OFF'].includes(status) ? '●' : '-'}</td>
                                    <td class="col-other">${!['PRD', 'SBY', 'UDT', 'PM', 'BKD', 'SDT', 'EGT', 'ENG', 'NST', 'OFF'].includes(status) ? '●' : '-'}</td>
                                    <td><span class="eq-status ${statusCat}">${status}</span></td>
                                </tr>
                            `;
                        });
                    }
                });
            }
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    function toggleFilter(checkbox, id) {
        const label = document.getElementById(id);
        if (checkbox.checked) {
            label.classList.add('active');
        } else {
            label.classList.remove('active');
        }
        loadData();
    }

    function getFilters() {
        const params = new URLSearchParams();

        const group = document.getElementById('filterGroup').value;
        if (group) params.append('workcenter_groups', group);

        if (document.querySelector('#chkProduction input').checked) {
            params.append('is_production', 'true');
        }
        if (document.querySelector('#chkKey input').checked) {
            params.append('is_key', 'true');
        }
        if (document.querySelector('#chkMonitor input').checked) {
            params.append('is_monitor', 'true');
        }

        return params.toString();
    }

    async function loadOptions() {
        try {
            const result = await MesApi.get('/api/resource/status/options', { silent: true });

            if (result.success) {
                const select = document.getElementById('filterGroup');
                workcenterGroups = result.data.workcenter_groups || [];

                workcenterGroups.forEach(group => {
                    const opt = document.createElement('option');
                    opt.value = group;
                    opt.textContent = group;
                    select.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('載入選項失敗:', e);
        }
    }

    async function loadSummary() {
        try {
            const queryString = getFilters();
            const endpoint = queryString
                ? `/api/resource/status/summary?${queryString}`
                : '/api/resource/status/summary';
            const result = await MesApi.get(endpoint, { silent: true });

            if (result.success) {
                const d = result.data;
                const total = d.total_count || 0;
                const status = d.by_status || {};

                // Get individual status counts
                const prd = status.PRD || 0;
                const sby = status.SBY || 0;
                const udt = status.UDT || 0;
                const sdt = status.SDT || 0;
                const egt = status.EGT || 0;
                const nst = status.NST || 0;

                // Calculate percentage denominator (includes NST)
                const totalStatus = prd + sby + udt + sdt + egt + nst;

                // Update OU% and AVAIL%
                const hasOuPct = d.ou_pct !== null && d.ou_pct !== undefined;
                const hasAvailPct = d.availability_pct !== null && d.availability_pct !== undefined;
                document.getElementById('ouPct').textContent = hasOuPct ? `${d.ou_pct}%` : '--';
                document.getElementById('availabilityPct').textContent = hasAvailPct ? `${d.availability_pct}%` : '--';

                // Update status cards with count and percentage
                document.getElementById('prdCount').textContent = prd;
                document.getElementById('prdPct').textContent = totalStatus ? `生產 (${((prd/totalStatus)*100).toFixed(1)}%)` : '生產';

                document.getElementById('sbyCount').textContent = sby;
                document.getElementById('sbyPct').textContent = totalStatus ? `待機 (${((sby/totalStatus)*100).toFixed(1)}%)` : '待機';

                document.getElementById('udtCount').textContent = udt;
                document.getElementById('udtPct').textContent = totalStatus ? `非計畫停機 (${((udt/totalStatus)*100).toFixed(1)}%)` : '非計畫停機';

                document.getElementById('sdtCount').textContent = sdt;
                document.getElementById('sdtPct').textContent = totalStatus ? `計畫停機 (${((sdt/totalStatus)*100).toFixed(1)}%)` : '計畫停機';

                document.getElementById('egtCount').textContent = egt;
                document.getElementById('egtPct').textContent = totalStatus ? `工程 (${((egt/totalStatus)*100).toFixed(1)}%)` : '工程';

                document.getElementById('nstCount').textContent = nst;
                document.getElementById('nstPct').textContent = totalStatus ? `未排程 (${((nst/totalStatus)*100).toFixed(1)}%)` : '未排程';

                // Update JOB count (equipment with active maintenance/repair job)
                const jobCount = d.with_active_job || 0;
                document.getElementById('jobCount').textContent = jobCount;

                // Update total count
                document.getElementById('totalCount').textContent = total;
            }
        } catch (e) {
            console.error('載入摘要失敗:', e);
        }
    }

    function loadMatrix() {
        // Matrix is now rendered from allEquipment data using hierarchy
        // This function is called after loadEquipment populates allEquipment
        renderMatrixHierarchy();
    }

    async function loadEquipment() {
        const container = document.getElementById('equipmentContainer');

        // Clear matrix filter when reloading data
        matrixFilter = null;
        document.getElementById('matrixFilterIndicator').classList.remove('active');

        try {
            const queryString = getFilters();
            const endpoint = queryString
                ? `/api/resource/status?${queryString}`
                : '/api/resource/status';
            const result = await MesApi.get(endpoint, { silent: true });

            if (result.success && result.data.length > 0) {
                allEquipment = result.data;
                document.getElementById('equipmentCount').textContent = result.count;
                renderEquipmentList(allEquipment);
            } else {
                allEquipment = [];
                document.getElementById('equipmentCount').textContent = 0;
                container.innerHTML = '<div class="empty-state">無符合條件的設備</div>';
            }
        } catch (e) {
            console.error('載入設備失敗:', e);
            container.innerHTML = '<div class="empty-state">載入失敗</div>';
        }
    }

    // ============================================================
    // Floating Tooltip Functions
    // ============================================================
    let currentTooltipData = null;

    function showTooltip(event, type, data) {
        event.stopPropagation();
        const tooltip = document.getElementById('floatingTooltip');
        const titleEl = document.getElementById('tooltipTitle');
        const contentEl = document.getElementById('tooltipContent');

        // Set content based on type
        if (type === 'lot') {
            titleEl.textContent = '在製批次明細';
            contentEl.innerHTML = renderLotContent(data);
        } else if (type === 'job') {
            titleEl.textContent = 'JOB 單詳細資訊';
            contentEl.innerHTML = renderJobContent(data);
        }

        // Position the tooltip
        tooltip.classList.add('show');

        // Get dimensions
        const rect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        // Calculate initial position near the click
        let x = event.clientX + 10;
        let y = event.clientY + 10;

        // Adjust if overflowing right
        if (x + rect.width > viewportWidth - 20) {
            x = event.clientX - rect.width - 10;
        }

        // Adjust if overflowing bottom
        if (y + rect.height > viewportHeight - 20) {
            y = viewportHeight - rect.height - 20;
        }

        // Ensure not off-screen left or top
        x = Math.max(10, x);
        y = Math.max(10, y);

        tooltip.style.left = x + 'px';
        tooltip.style.top = y + 'px';

        currentTooltipData = { type, data };
    }

    function hideTooltip() {
        const tooltip = document.getElementById('floatingTooltip');
        tooltip.classList.remove('show');
        currentTooltipData = null;
    }

    // Close tooltip when clicking outside
    document.addEventListener('click', (e) => {
        const tooltip = document.getElementById('floatingTooltip');
        if (tooltip && !tooltip.contains(e.target) && !e.target.classList.contains('info-trigger')) {
            hideTooltip();
        }
    });

    // Helper functions to show specific tooltip types
    function showLotTooltip(event, resourceId) {
        const eq = allEquipment.find(e => e.RESOURCEID === resourceId);
        if (eq && eq.LOT_DETAILS) {
            showTooltip(event, 'lot', eq.LOT_DETAILS);
        }
    }

    function showJobTooltip(event, resourceId) {
        const eq = allEquipment.find(e => e.RESOURCEID === resourceId);
        if (eq && eq.JOBORDER) {
            showTooltip(event, 'job', eq);
        }
    }

    function renderLotContent(lotDetails) {
        if (!lotDetails || lotDetails.length === 0) return '<div style="color: #94a3b8;">無批次資料</div>';

        let html = '<div class="lot-tooltip-content">';
        lotDetails.forEach(lot => {
            const trackinTime = lot.LOTTRACKINTIME ? new Date(lot.LOTTRACKINTIME).toLocaleString('zh-TW') : '--';
            const qty = lot.LOTTRACKINQTY_PCS != null ? lot.LOTTRACKINQTY_PCS.toLocaleString() : '--';
            html += `
                <div class="lot-item">
                    <div class="lot-item-header">${lot.RUNCARDLOTID || '--'}</div>
                    <div class="lot-item-row">
                        <div class="lot-item-field"><span class="lot-item-label">數量:</span><span class="lot-item-value">${qty} pcs</span></div>
                        <div class="lot-item-field"><span class="lot-item-label">TrackIn:</span><span class="lot-item-value">${trackinTime}</span></div>
                        <div class="lot-item-field"><span class="lot-item-label">操作員:</span><span class="lot-item-value">${lot.LOTTRACKINEMPLOYEE || '--'}</span></div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        return html;
    }

    function renderJobContent(eq) {
        const formatDate = (dateStr) => {
            if (!dateStr) return '--';
            try {
                return new Date(dateStr).toLocaleString('zh-TW');
            } catch {
                return dateStr;
            }
        };

        const field = (label, value, isHighlight = false) => {
            const valueClass = isHighlight ? 'highlight' : '';
            return `
                <div class="job-detail-field">
                    <span class="job-detail-label">${label}</span>
                    <span class="job-detail-value ${valueClass}">${value || '--'}</span>
                </div>
            `;
        };

        return `
            <div class="job-detail-grid">
                ${field('JOBORDER', eq.JOBORDER, true)}
                ${field('JOBSTATUS', eq.JOBSTATUS, true)}
                ${field('JOBMODEL', eq.JOBMODEL)}
                ${field('JOBSTAGE', eq.JOBSTAGE)}
                ${field('JOBID', eq.JOBID)}
                ${field('建立時間', formatDate(eq.CREATEDATE))}
                ${field('建立人員', eq.CREATEUSERNAME || eq.CREATEUSER)}
                ${field('技術員', eq.TECHNICIANUSERNAME || eq.TECHNICIANUSER)}
                ${field('症狀碼', eq.SYMPTOMCODE)}
                ${field('原因碼', eq.CAUSECODE)}
                ${field('維修碼', eq.REPAIRCODE)}
            </div>
        `;
    }

    function renderEquipmentList(equipment) {
        const container = document.getElementById('equipmentContainer');

        if (equipment.length === 0) {
            container.innerHTML = '<div class="empty-state">無符合條件的設備</div>';
            return;
        }

        let html = '<div class="equipment-grid">';

        equipment.forEach((eq) => {
            const statusCat = (eq.STATUS_CATEGORY || 'OTHER').toLowerCase();
            const statusDisplay = getStatusDisplay(eq.EQUIPMENTASSETSSTATUS, eq.STATUS_CATEGORY);
            const resourceId = eq.RESOURCEID || '';
            const escapedResourceId = resourceId.replace(/'/g, "\\'");

            // Build LOT info with click trigger
            let lotHtml = '';
            if (eq.LOT_COUNT > 0) {
                lotHtml = `<span class="info-trigger" onclick="showLotTooltip(event, '${escapedResourceId}')" title="點擊查看批次詳情">📦 ${eq.LOT_COUNT} 批</span>`;
            }

            // Build JOB info with click trigger
            let jobHtml = '';
            if (eq.JOBORDER) {
                jobHtml = `<span class="info-trigger" onclick="showJobTooltip(event, '${escapedResourceId}')" title="點擊查看JOB詳情">📋 ${eq.JOBORDER}</span>`;
            }

            html += `
                <div class="equipment-card status-${statusCat}">
                    <div class="eq-header">
                        <div class="eq-name">${eq.RESOURCENAME || eq.RESOURCEID || '--'}</div>
                        <span class="eq-status ${statusCat}">${statusDisplay}</span>
                    </div>
                    <div class="eq-info">
                        <span title="工站">📍 ${eq.WORKCENTERNAME || '--'}</span>
                        <span title="群組">🏭 ${eq.WORKCENTER_GROUP || '--'}</span>
                        <span title="家族">🔧 ${eq.RESOURCEFAMILYNAME || '--'}</span>
                        <span title="區域">🏢 ${eq.LOCATIONNAME || '--'}</span>
                        ${lotHtml}
                        ${jobHtml}
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;
    }

    function filterByMatrixCell(workcenterGroup, status, family = null, resource = null) {
        // Toggle off if clicking same cell (exact match including family and resource)
        if (matrixFilter &&
            matrixFilter.workcenter_group === workcenterGroup &&
            matrixFilter.status === status &&
            matrixFilter.family === family &&
            matrixFilter.resource === resource) {
            clearMatrixFilter();
            return;
        }

        matrixFilter = {
            workcenter_group: workcenterGroup,
            status: status,
            family: family,
            resource: resource
        };

        // Update selected cell highlighting for group and family level cells
        document.querySelectorAll('.matrix-table td.clickable').forEach(cell => {
            cell.classList.remove('selected');
            const cellWg = cell.dataset.wg;
            const cellStatus = cell.dataset.status;
            const cellFam = cell.dataset.fam;

            // Match based on level
            if (cellWg === workcenterGroup && cellStatus === status) {
                if (family === null && resource === null && !cellFam) {
                    // Group level match
                    cell.classList.add('selected');
                } else if (family !== null && cellFam === family && resource === null) {
                    // Family level match
                    cell.classList.add('selected');
                }
            }
        });

        // Update selected row highlighting for equipment level
        document.querySelectorAll('.matrix-table tr.clickable-row').forEach(row => {
            row.classList.remove('selected');
            if (resource !== null && row.dataset.res === resource) {
                row.classList.add('selected');
            }
        });

        // Show filter indicator with hierarchical label
        const statusLabels = {
            'PRD': '生產中',
            'SBY': '待機',
            'UDT': '非計畫停機',
            'SDT': '計畫停機',
            'EGT': '工程',
            'NST': '未排程',
            'OTHER': '其他'
        };

        let filterLabel = workcenterGroup;
        if (family) filterLabel += ` / ${family}`;
        if (resource) {
            // Find resource name from allEquipment
            const eqInfo = allEquipment.find(e => e.RESOURCEID === resource);
            const resName = eqInfo ? (eqInfo.RESOURCENAME || resource) : resource;
            filterLabel += ` / ${resName}`;
        }
        filterLabel += ` - ${statusLabels[status] || status}`;

        document.getElementById('matrixFilterText').textContent = filterLabel;
        document.getElementById('matrixFilterIndicator').classList.add('active');

        // Filter and render equipment list
        // Use same grouping logic as buildMatrixHierarchy
        const filtered = allEquipment.filter(eq => {
            // Match workcenter group
            const eqGroup = eq.WORKCENTER_GROUP || 'UNKNOWN';
            if (eqGroup !== workcenterGroup) return false;

            // Match family if specified
            if (family !== null) {
                const eqFamily = eq.RESOURCEFAMILYNAME || 'UNKNOWN';
                if (eqFamily !== family) return false;
            }

            // Match resource if specified
            if (resource !== null) {
                if (eq.RESOURCEID !== resource) return false;
            }

            // Match status based on EQUIPMENTASSETSSTATUS (same logic as matrix calculation)
            const eqStatus = eq.EQUIPMENTASSETSSTATUS || '';

            // Map equipment status to matrix status category (same as buildMatrixHierarchy)
            let eqStatusKey = 'OTHER';
            if (['PRD'].includes(eqStatus)) eqStatusKey = 'PRD';
            else if (['SBY'].includes(eqStatus)) eqStatusKey = 'SBY';
            else if (['UDT', 'PM', 'BKD'].includes(eqStatus)) eqStatusKey = 'UDT';
            else if (['SDT'].includes(eqStatus)) eqStatusKey = 'SDT';
            else if (['EGT', 'ENG'].includes(eqStatus)) eqStatusKey = 'EGT';
            else if (['NST', 'OFF'].includes(eqStatus)) eqStatusKey = 'NST';

            return eqStatusKey === status;
        });

        document.getElementById('equipmentCount').textContent = filtered.length;
        renderEquipmentList(filtered);
    }

    function clearMatrixFilter() {
        matrixFilter = null;

        // Remove selected highlighting from cells
        document.querySelectorAll('.matrix-table td.clickable').forEach(cell => {
            cell.classList.remove('selected');
        });

        // Remove selected highlighting from rows
        document.querySelectorAll('.matrix-table tr.clickable-row').forEach(row => {
            row.classList.remove('selected');
        });

        // Hide filter indicator
        document.getElementById('matrixFilterIndicator').classList.remove('active');

        // Show all equipment
        document.getElementById('equipmentCount').textContent = allEquipment.length;
        renderEquipmentList(allEquipment);
    }

    function getStatusDisplay(status, category) {
        const statusMap = {
            'PRD': '生產中',
            'SBY': '待機',
            'UDT': '非計畫停機',
            'SDT': '計畫停機',
            'EGT': '工程',
            'NST': '未排程'
        };

        if (status && statusMap[status]) {
            return statusMap[status];
        }

        const catMap = {
            'PRODUCTIVE': '生產中',
            'STANDBY': '待機',
            'DOWN': '停機',
            'ENGINEERING': '工程',
            'NOT_SCHEDULED': '未排程',
            'INACTIVE': '停用'
        };

        return catMap[category] || status || '--';
    }

    async function checkCacheStatus() {
        try {
            const data = await MesApi.get('/health', {
                silent: true,
                retries: 0,
                timeout: 15000
            });

            const dot = document.getElementById('cacheDot');
            const status = document.getElementById('cacheStatus');
            const resCache = data.resource_cache || {};
            const eqCache = data.equipment_status_cache || {};

            // 使用 resource_cache 的數量（過濾後的設備數）
            if (resCache.enabled && resCache.loaded) {
                dot.className = 'cache-dot';
                status.textContent = `快取正常 (${resCache.count} 筆)`;
            } else if (resCache.enabled) {
                dot.className = 'cache-dot loading';
                status.textContent = '快取載入中...';
            } else {
                dot.className = 'cache-dot error';
                status.textContent = '快取未啟用';
            }

            // 使用 equipment_status_cache 的更新時間（即時狀態更新時間）
            if (eqCache.updated_at) {
                document.getElementById('lastUpdate').textContent =
                    `更新: ${new Date(eqCache.updated_at).toLocaleString('zh-TW')}`;
            }
        } catch (e) {
            document.getElementById('cacheDot').className = 'cache-dot error';
            document.getElementById('cacheStatus').textContent = '無法連線';
        }
    }

    async function loadData() {
        const btn = document.getElementById('btnRefresh');
        btn.disabled = true;

        try {
            // loadSummary can run in parallel
            // loadEquipment must complete before loadMatrix (matrix uses allEquipment data)
            await Promise.all([
                loadSummary(),
                loadEquipment()
            ]);
            // Now render the matrix from the loaded equipment data
            loadMatrix();
        } finally {
            btn.disabled = false;
        }
    }

    // ============================================================
    // Auto-refresh
    // ============================================================
    const REFRESH_INTERVAL = 5 * 60 * 1000;  // 5 minutes
    let refreshTimer = null;

    function startAutoRefresh() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
        }
        console.log('[Resource Status] Auto-refresh started, interval:', REFRESH_INTERVAL / 1000, 'seconds');
        refreshTimer = setInterval(() => {
            if (!document.hidden) {
                console.log('[Resource Status] Auto-refresh triggered at', new Date().toLocaleTimeString());
                checkCacheStatus();
                loadData();
            } else {
                console.log('[Resource Status] Auto-refresh skipped (tab hidden)');
            }
        }, REFRESH_INTERVAL);
    }

    // Handle page visibility - refresh when tab becomes visible
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            console.log('[Resource Status] Tab became visible, refreshing...');
            checkCacheStatus();
            loadData();
            startAutoRefresh();
        }
    });

    // Initialize
    document.addEventListener('DOMContentLoaded', async () => {
        await loadOptions();
        await checkCacheStatus();
        await loadData();

        // Start auto-refresh
        startAutoRefresh();
    });

Object.assign(window, {
buildMatrixHierarchy,
toggleMatrixRow,
toggleAllMatrixRows,
renderMatrixHierarchy,
toggleFilter,
getFilters,
loadOptions,
loadSummary,
loadMatrix,
loadEquipment,
showTooltip,
hideTooltip,
showLotTooltip,
showJobTooltip,
renderLotContent,
renderJobContent,
renderEquipmentList,
filterByMatrixCell,
clearMatrixFilter,
getStatusDisplay,
checkCacheStatus,
loadData,
startAutoRefresh,
});
