<script setup lang="ts">
import { computed, ref, watch } from 'vue';

interface Props {
  startDate?: string;
  endDate?: string;
  holdType?: string;
  mode?: string;
  todayModeEnabled?: boolean;
  disabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  startDate: '',
  endDate: '',
  holdType: 'quality',
  mode: 'range',
  todayModeEnabled: true,
  disabled: false,
});

const emit = defineEmits<{
  apply: [payload: { startDate: string; endDate: string }];
  'hold-type-change': [holdType: string];
  'mode-change': [mode: string];
}>();

const localStartDate = ref(props.startDate);
const localEndDate = ref(props.endDate);

watch(() => props.startDate, (v) => { localStartDate.value = v; });
watch(() => props.endDate, (v) => { localEndDate.value = v; });

const holdTypeModel = computed({
  get() { return props.holdType || 'quality'; },
  set(nextValue) { emit('hold-type-change', nextValue || 'quality'); },
});

function handleApply(): void {
  emit('apply', {
    startDate: localStartDate.value,
    endDate: localEndDate.value,
  });
}

function setMode(newMode: string): void {
  if (newMode !== props.mode) {
    emit('mode-change', newMode);
  }
}
</script>

<template>
  <section class="filter-bar card">
    <div v-if="todayModeEnabled" class="filter-group mode-toggle-group">
      <span class="filter-label">查詢模式</span>
      <div class="mode-toggle" role="group" aria-label="查詢模式切換">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: mode === 'range' }"
          :disabled="disabled"
          :title="'日期區間：選取日期範圍查看歷史 Hold / Release 事件'"
          @click="setMode('range')"
        >
          日期區間
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: mode === 'today' }"
          :disabled="disabled"
          :title="'當日：查看當下所有 On Hold lot 及今日新增 / Release 動態，每 60 秒自動刷新'"
          @click="setMode('today')"
        >
          當日
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: mode === 'current' }"
          :disabled="disabled"
          :title="'現況：查看即時 On Hold 狀態及本班次新增/Release 動態，每 60 秒自動刷新'"
          @click="setMode('current')"
        >
          現況
        </button>
      </div>
    </div>

    <template v-if="mode === 'range'">
      <div class="filter-group date-group">
        <label class="filter-label" for="hold-history-start-date">開始日期</label>
        <input
          id="hold-history-start-date"
          v-model="localStartDate"
          class="date-input"
          type="date"
          :disabled="disabled"
        />
      </div>

      <div class="filter-group date-group">
        <label class="filter-label" for="hold-history-end-date">結束日期</label>
        <input
          id="hold-history-end-date"
          v-model="localEndDate"
          class="date-input"
          type="date"
          :disabled="disabled"
        />
      </div>
    </template>

    <template v-else>
      <div class="filter-group date-group date-group--today-placeholder">
        <span class="filter-label">資料日期</span>
        <span class="today-date-badge" title="日期由 server SYSDATE 推算（07:30 班別切換）">今日（伺服器時間）</span>
      </div>
    </template>

    <div class="filter-group hold-type-group">
      <label class="filter-label" for="hold-history-hold-type">Hold Type</label>
      <select
        id="hold-history-hold-type"
        v-model="holdTypeModel"
        class="hold-type-select"
        :disabled="disabled"
      >
        <option value="quality">品質異常</option>
        <option value="non-quality">非品質異常</option>
        <option value="all">全部</option>
      </select>
    </div>

    <div v-if="mode === 'range'" class="filter-group filter-action-group">
      <button
        type="button"
        class="ui-btn ui-btn--primary"
        :disabled="disabled"
        @click="handleApply"
      >
        <template v-if="disabled">查詢中...</template>
        <template v-else>查詢</template>
      </button>
    </div>
  </section>
</template>
