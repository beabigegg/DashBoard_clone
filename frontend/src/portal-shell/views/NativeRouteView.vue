<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
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
  renderMode: {
    type: String,
    default: 'native',
  },
});

const route = useRoute();
const launchHref = computed(() => buildLaunchHref(props.targetRoute, route.query));
const moduleLoading = ref(true);
const moduleError = ref('');
const resolvedComponent = ref(null);
const MODULE_RECOVERY_KEY = 'portal-shell:native-module-recovered';
const MODULE_RECOVERY_TTL_MS = 2 * 60 * 1000;
const MODULE_LOAD_TIMEOUT_MS = 15000;
const loadingElapsed = ref(0);
let loadingTimer = null;

function startLoadingTimer() {
  loadingElapsed.value = 0;
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    loadingElapsed.value += 1;
  }, 1000);
}

function stopLoadingTimer() {
  clearInterval(loadingTimer);
  loadingTimer = null;
}

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
  startLoadingTimer();

  if (props.renderMode === 'external') {
    moduleLoading.value = false;
    stopLoadingTimer();
    openLegacyPage();
    return;
  }

  const loader = getNativeModuleLoader(route);
  if (!loader) {
    moduleLoading.value = false;
    stopLoadingTimer();
    return;
  }

  try {
    const loadPromise = loader();
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('MODULE_LOAD_TIMEOUT')), MODULE_LOAD_TIMEOUT_MS);
    });
    const module = await Promise.race([loadPromise, timeoutPromise]);
    resolvedComponent.value = module?.default || null;
    if (!resolvedComponent.value) {
      moduleError.value = `Native module missing default export: ${route}`;
    }
  } catch (error) {
    if (error?.message === 'MODULE_LOAD_TIMEOUT') {
      moduleError.value = `模組載入逾時 (${MODULE_LOAD_TIMEOUT_MS / 1000}s)，網路可能較慢`;
    } else if (shouldRecoverWithReload(error) && recoverByReloadOnce()) {
      return;
    } else {
      moduleError.value = error?.message || `Failed to load native module: ${route}`;
    }
  } finally {
    moduleLoading.value = false;
    stopLoadingTimer();
  }
}

watch(
  () => [props.targetRoute, props.renderMode],
  ([route]) => {
    void loadNativeModule(route);
  },
);

onMounted(() => {
  void loadNativeModule(props.targetRoute);
});

onUnmounted(() => {
  stopLoadingTimer();
});
</script>

<template>
  <div v-if="moduleLoading" class="panel">
    <h2>{{ pageName }}</h2>
    <p>載入 native route-view 模組中...{{ loadingElapsed >= 3 ? ` (${loadingElapsed}s)` : '' }}</p>
  </div>

  <Transition v-else-if="resolvedComponent" name="page-fade" mode="out-in">
    <component
      :is="resolvedComponent"
      :key="targetRoute"
    />
  </Transition>

  <div v-else class="panel">
    <h2>{{ pageName }}</h2>
    <p v-if="drawerName">分類：{{ drawerName }}</p>
    <p v-if="moduleError">Native 模組載入失敗：{{ moduleError }}</p>
    <p v-else>Native route-view integration 已啟用契約，但此頁仍暫時以既有頁面承載內容。</p>
    <p v-if="owner" class="muted">Owner: {{ owner }}</p>
    <div class="actions">
      <button
        v-if="moduleError"
        type="button"
        class="ui-btn ui-btn--primary ui-btn--sm"
        @click="loadNativeModule(targetRoute)"
      >
        重試載入
      </button>
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" @click="openLegacyPage">開啟既有頁面</button>
      <a class="btn-link" :href="launchHref">直接前往 {{ launchHref }}</a>
    </div>
  </div>
</template>

<style>
.page-fade-enter-active {
  transition: opacity var(--motion-normal) var(--motion-ease), transform var(--motion-normal) var(--motion-ease);
}
.page-fade-leave-active {
  transition: opacity var(--motion-fast) var(--motion-ease);
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .page-fade-enter-active,
  .page-fade-leave-active {
    transition-duration: 0ms;
  }
}
</style>
