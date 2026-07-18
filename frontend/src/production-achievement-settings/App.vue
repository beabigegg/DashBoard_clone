<script setup lang="ts">
/**
 * production-achievement-settings — standalone mini-app administering the 2
 * remaining MySQL config tables for the 生產達成率 report (production-
 * achievement-overhaul, IP-9; production-achievement-oracle-plan-source
 * removed the 3rd — 每日計畫/daily-plans, now Oracle-sourced, PA-11).
 * Standalone drilldown route (D4, design.md), reached only via the report
 * page's 設定 button — no drawer entry.
 *
 * Smart page (this file): fetches both GETs, owns the shared fail-closed
 * `editForbidden` state + OD-5 save note; the 2 panels below are dumb
 * components (props in, events out) — mirrors admin-dashboard's
 * PermissionsTab.vue/TargetPermissionsPanel.vue split and
 * TargetEditPanel.vue's inline-edit shape.
 *
 * OD-6: no unsaved-edit navigation guard (matches TargetEditPanel precedent —
 * nothing here listens for beforeunload/route-leave).
 */
import { onMounted } from 'vue';
import { useProductionAchievementSettings, type PlanSourceSide } from './composables/useProductionAchievementSettings';
import { navigateToRuntimeRoute } from '../core/shell-navigation';
import BlockLoadingState from '../shared-ui/components/BlockLoadingState.vue';
import PackageLfMappingPanel from './components/PackageLfMappingPanel.vue';
import WorkcenterMergeMappingPanel from './components/WorkcenterMergeMappingPanel.vue';

const {
  packageLfMap,
  loading,
  editForbidden,
  editError,
  editSaving,
  saveNote,
  workcenterFullList,
  packageLfUnmappedHints,
  fetchAll,
  savePackageLf,
  deletePackageLf,
  saveWorkcenterMerge,
  excludeWorkcenterGroup,
  dismissSaveNote,
} = useProductionAchievementSettings();

onMounted(() => {
  void fetchAll();
});

function goBackToReport(): void {
  navigateToRuntimeRoute('/production-achievement');
}

async function handleSavePackageLf(payload: { raw_package_lf: string; merged_group: string }): Promise<void> {
  await savePackageLf(payload);
}

async function handleDeletePackageLf(raw: string): Promise<void> {
  await deletePackageLf(raw);
}

async function handleIncludeWorkcenter(payload: { raw_workcenter_group: string; merged_workcenter_group: string; parent_group?: string; plan_source_side: PlanSourceSide }): Promise<void> {
  await saveWorkcenterMerge(payload);
}

async function handleExcludeWorkcenter(raw: string): Promise<void> {
  await excludeWorkcenterGroup(raw);
}

async function handleRenameWorkcenter(payload: { raw_workcenter_group: string; merged_workcenter_group: string; parent_group?: string; plan_source_side: PlanSourceSide }): Promise<void> {
  await saveWorkcenterMerge(payload);
}
</script>

<template>
  <div class="theme-production-achievement-settings pa-settings__page" data-testid="pa-settings-app">
    <div class="ui-card pa-settings__header-card">
      <div class="ui-card-header">
        <span class="ui-card-title">生產達成率 — 對照設定</span>
        <button type="button" class="ui-btn ui-btn--secondary ui-btn--sm" data-testid="pa-settings-back-btn" @click="goBackToReport">
          ← 返回報表
        </button>
      </div>
    </div>

    <!-- OD-5: shown once after ANY successful write across the 3 panels below. -->
    <div v-if="saveNote" class="pa-settings__save-note" role="status" data-testid="pa-settings-save-note">
      <span>{{ saveNote }}</span>
      <button type="button" class="pa-settings__save-note-dismiss" aria-label="關閉提示" data-testid="pa-settings-save-note-dismiss" @click="dismissSaveNote">
        ✕
      </button>
    </div>

    <BlockLoadingState v-if="loading" data-testid="pa-settings-loading" />

    <template v-else>
      <PackageLfMappingPanel
        :rows="packageLfMap"
        :unmapped-hints="packageLfUnmappedHints"
        :edit-forbidden="editForbidden"
        :edit-error="editError"
        :edit-saving="editSaving"
        @save="handleSavePackageLf"
        @delete="handleDeletePackageLf"
      />

      <WorkcenterMergeMappingPanel
        :full-list="workcenterFullList"
        :edit-forbidden="editForbidden"
        :edit-error="editError"
        :edit-saving="editSaving"
        @include="handleIncludeWorkcenter"
        @exclude="handleExcludeWorkcenter"
        @rename="handleRenameWorkcenter"
      />
    </template>
  </div>
</template>
