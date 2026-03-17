<script setup>
import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();

const visible = ref(false);
const totalCount = ref(0);
const severity = ref('ok');

let pollTimer = null;

async function fetchSummary() {
  try {
    const resp = await fetch('/api/analytics/anomaly-summary');
    if (resp.status === 404) {
      // Feature flag off — keep hidden
      return;
    }
    if (!resp.ok) {
      return;
    }
    const payload = await resp.json();
    if (payload.success && payload.data) {
      totalCount.value = payload.data.total_count ?? 0;
      severity.value = payload.data.severity ?? 'ok';
      visible.value = true;
    }
  } catch {
    // Non-critical; keep last known state
  }
}

function handleClick() {
  router.push('/anomaly-overview');
}

onMounted(() => {
  void fetchSummary();
  pollTimer = setInterval(() => void fetchSummary(), 30_000);
});

onUnmounted(() => {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
});
</script>

<template>
  <div v-if="visible" class="anomaly-indicator-wrap">
    <button type="button" class="anomaly-trigger" @click="handleClick">
      <span class="dot" :class="[`anomaly-dot-${severity}`, severity === 'critical' ? 'critical-pulse' : '']"></span>
      <span class="anomaly-count">{{ totalCount }}</span>
    </button>
  </div>
</template>
