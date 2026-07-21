<script setup lang="ts">
import { useRouter } from 'vue-router';

import ParetoSection from '../../wip-shared/components/ParetoSection.vue';
import type { WipItem } from '../../core/wip-derive';

defineProps<{
  quality: WipItem[];
  nonQuality: WipItem[];
}>();

const router = useRouter();

function goToHoldOverview(): void {
  router.push('/hold-overview');
}
</script>

<template>
  <section class="card ui-card" data-testid="dashboard-hold-section">
    <div
      class="card-header ui-card-header dh-card-header--nav"
      role="button"
      tabindex="0"
      title="前往 Hold 即時概況"
      @click="goToHoldOverview"
      @keydown.enter="goToHoldOverview"
      @keydown.space.prevent="goToHoldOverview"
    >
      <div class="card-title ui-card-title">Hold 異常概況</div>
      <span class="dh-nav-arrow" aria-hidden="true">›</span>
    </div>
    <div class="card-body ui-card-body">
      <div class="pareto-grid">
        <ParetoSection type="quality" title="品質異常 Hold" :items="quality" />
        <ParetoSection type="non-quality" title="非品質異常 Hold" :items="nonQuality" />
      </div>
    </div>
  </section>
</template>
