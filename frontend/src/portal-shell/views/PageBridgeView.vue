<script setup>
import { computed } from 'vue';

const props = defineProps({
  targetRoute: {
    type: String,
    required: true,
  },
  pageName: {
    type: String,
    required: true,
  },
  drawerName: {
    type: String,
    default: '',
  },
});

const launchHref = computed(() => props.targetRoute || '/');

function launch() {
  window.location.href = launchHref.value;
}
</script>

<template>
  <div class="panel">
    <h2>{{ pageName }}</h2>
    <p v-if="drawerName">分類：{{ drawerName }}</p>
    <p>此頁已建立 router 導航掛載點。下一階段將逐步把內容整合至 shell route view。</p>
    <div class="actions">
      <button type="button" class="btn-primary" @click="launch">開啟既有頁面</button>
      <a class="btn-link" :href="launchHref">直接前往 {{ launchHref }}</a>
    </div>
  </div>
</template>
