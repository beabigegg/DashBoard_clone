<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { getNativeModuleLoader } from '../nativeModuleRegistry.js';
import { buildLaunchHref } from '../routeQuery.js';

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
  owner: {
    type: String,
    default: '',
  },
});

const route = useRoute();
const launchHref = computed(() => buildLaunchHref(props.targetRoute, route.query));
const moduleLoading = ref(true);
const moduleError = ref('');
const resolvedComponent = ref(null);
const MODULE_RECOVERY_KEY = 'portal-shell:native-module-recovered';
const MODULE_RECOVERY_TTL_MS = 2 * 60 * 1000;

function shouldRecoverWithReload(error) {
  const message = String(error?.message || error || '').toLowerCase();
  return [
    'failed to fetch dynamically imported module',
    'error loading dynamically imported module',
    'importing a module script failed',
    'loading css chunk',
    'unable to preload css',
  ].some((keyword) => message.includes(keyword));
}

function recoverByReloadOnce() {
  const currentUrl = window.location.href;
  try {
    const raw = window.sessionStorage.getItem(MODULE_RECOVERY_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      const recoveredUrl = String(parsed?.url || '');
      const recoveredAt = Number(parsed?.at || 0);
      if (recoveredUrl === currentUrl && Date.now() - recoveredAt < MODULE_RECOVERY_TTL_MS) {
        return false;
      }
    }
  } catch {
    // Ignore parse errors and proceed with recovery attempt.
  }

  window.sessionStorage.setItem(
    MODULE_RECOVERY_KEY,
    JSON.stringify({
      url: currentUrl,
      at: Date.now(),
    }),
  );
  window.location.reload();
  return true;
}

function openLegacyPage() {
  window.location.href = launchHref.value;
}

async function loadNativeModule(route) {
  moduleLoading.value = true;
  moduleError.value = '';
  resolvedComponent.value = null;

  const loader = getNativeModuleLoader(route);
  if (!loader) {
    moduleLoading.value = false;
    return;
  }

  try {
    const module = await loader();
    resolvedComponent.value = module?.default || null;
    if (!resolvedComponent.value) {
      moduleError.value = `Native module missing default export: ${route}`;
    }
  } catch (error) {
    if (shouldRecoverWithReload(error) && recoverByReloadOnce()) {
      return;
    }
    moduleError.value = error?.message || `Failed to load native module: ${route}`;
  } finally {
    moduleLoading.value = false;
  }
}

watch(
  () => props.targetRoute,
  (route) => {
    void loadNativeModule(route);
  },
);

onMounted(() => {
  void loadNativeModule(props.targetRoute);
});
</script>

<template>
  <div v-if="moduleLoading" class="panel">
    <h2>{{ pageName }}</h2>
    <p>載入 native route-view 模組中...</p>
  </div>

  <component
    :is="resolvedComponent"
    v-else-if="resolvedComponent"
  />

  <div v-else class="panel">
    <h2>{{ pageName }}</h2>
    <p v-if="drawerName">分類：{{ drawerName }}</p>
    <p v-if="moduleError">Native 模組載入失敗：{{ moduleError }}</p>
    <p v-else>Native route-view integration 已啟用契約，但此頁仍暫時以既有頁面承載內容。</p>
    <p v-if="owner" class="muted">Owner: {{ owner }}</p>
    <div class="actions">
      <button type="button" class="btn-primary" @click="openLegacyPage">開啟既有頁面</button>
      <a class="btn-link" :href="launchHref">直接前往 {{ launchHref }}</a>
    </div>
  </div>
</template>
