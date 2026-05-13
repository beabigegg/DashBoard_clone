<script setup lang="ts">
import { computed } from 'vue';

interface AgeCard { range?: string; lots: number; qty: number; percentage: number; }

const props = defineProps({
  items: {
    type: Array as () => AgeCard[],
    default: () => [],
  },
  activeRange: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

const cardRanges = ['0-1', '1-3', '3-7', '7+'];

const ageMap = computed(() => {
  const map: Record<string, AgeCard> = {};
  props.items.forEach((item: AgeCard) => {
    if (item?.range) {
      map[item.range] = item;
    }
  });
  return map;
});

function getCard(range: string): AgeCard {
  return ageMap.value[range] || { lots: 0, qty: 0, percentage: 0 };
}

function formatNumber(value: number | undefined): string {
  return Number(value || 0).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="age-distribution">
    <article
      v-for="range in cardRanges"
      :key="range"
      class="age-card"
      :class="{ active: activeRange === range }"
      @click="emit('toggle', range)"
    >
      <div class="age-label">{{ range }}天</div>
      <div class="age-stats">
        <div class="age-stat">
          <span class="label">Lots</span>
          <span class="value">{{ formatNumber(getCard(range).lots) }}</span>
        </div>
        <div class="age-stat">
          <span class="label">QTY</span>
          <span class="value">{{ formatNumber(getCard(range).qty) }}</span>
        </div>
      </div>
      <div class="age-percentage">{{ getCard(range).percentage || 0 }}%</div>
    </article>
  </section>
</template>
