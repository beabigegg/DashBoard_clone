<script setup>
const props = defineProps({
  categories: {
    type: Array,
    default: () => [],
  },
  selectedTableName: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['select-table']);

function formatRowCount(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '--';
  }
  return parsed.toLocaleString('zh-TW');
}

function resolveDisplayName(table) {
  return table?.display_name || table?.name || '--';
}

function handleSelect(table) {
  if (props.disabled || !table?.name) {
    return;
  }
  emit('select-table', table);
}
</script>

<template>
  <section class="table-catalog">
    <div
      v-for="category in categories"
      :key="category.name"
      class="table-category"
    >
      <h2 class="category-title">{{ category.name }}</h2>
      <div class="table-grid">
        <article
          v-for="table in category.tables"
          :key="table.name"
          class="table-card"
          :class="{
            active: table.name === selectedTableName,
            disabled,
          }"
          role="button"
          tabindex="0"
          @click="handleSelect(table)"
          @keydown.enter.prevent="handleSelect(table)"
          @keydown.space.prevent="handleSelect(table)"
        >
          <h3 class="table-name">
            {{ resolveDisplayName(table) }}
            <span v-if="Number(table.row_count || 0) > 10000000" class="badge large">大表</span>
          </h3>
          <p class="table-info">數據量: {{ formatRowCount(table.row_count) }} 行</p>
          <p v-if="table.time_field" class="table-info">時間欄位: {{ table.time_field }}</p>
          <p class="table-desc">{{ table.description || '無描述' }}</p>
        </article>
      </div>
    </div>
  </section>
</template>
