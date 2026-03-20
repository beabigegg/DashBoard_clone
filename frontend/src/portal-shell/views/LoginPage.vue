<script setup>
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuth } from '../composables/useAuth.js';
import { setAuthState } from '../router.js';

const router = useRouter();
const route = useRoute();
const { login, startHeartbeat } = useAuth();

const username = ref('');
const password = ref('');
const errorMsg = ref('');
const loading = ref(false);

async function handleSubmit() {
  errorMsg.value = '';
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '請輸入帳號和密碼';
    return;
  }

  loading.value = true;
  try {
    const result = await login(username.value.trim(), password.value);
    if (result.success) {
      setAuthState(true);
      startHeartbeat();
      let next = route.query.next || '/';
      if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//')) {
        next = '/';
      }
      await router.push(next);
    } else {
      errorMsg.value = result.error?.message || '帳號或密碼錯誤';
    }
  } catch {
    errorMsg.value = '登入失敗，請稍後再試';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center login-bg">
    <div class="bg-white rounded-xl p-10 w-full max-w-[400px] shadow-2xl">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-gray-800 mb-2">MES 報表系統</h1>
        <p class="text-gray-500 text-sm">請使用員工帳號登入</p>
      </div>

      <form class="flex flex-col gap-5" @submit.prevent="handleSubmit">
        <div class="flex flex-col gap-1.5">
          <label for="username" class="text-sm font-medium text-gray-700">帳號（工號）</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="請輸入工號"
            autocomplete="username"
            :disabled="loading"
            class="px-3.5 py-2.5 border border-gray-300 rounded-md text-[0.9375rem] outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>

        <div class="flex flex-col gap-1.5">
          <label for="password" class="text-sm font-medium text-gray-700">密碼</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="請輸入密碼"
            autocomplete="current-password"
            :disabled="loading"
            class="px-3.5 py-2.5 border border-gray-300 rounded-md text-[0.9375rem] outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>

        <div v-if="errorMsg" class="px-3.5 py-2.5 bg-red-50 border border-red-200 rounded-md text-red-600 text-sm" role="alert">
          {{ errorMsg }}
        </div>

        <button type="submit" class="login-btn" :disabled="loading">
          <span v-if="loading">登入中...</span>
          <span v-else>登入</span>
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-bg {
  background: linear-gradient(135deg, theme('colors.gray.800') 0%, theme('colors.gray.900') 100%);
}

.login-btn {
  @apply py-3 text-white border-0 rounded-md text-base font-semibold cursor-pointer;
  background: linear-gradient(135deg, theme('colors.blue.600') 0%, theme('colors.blue.700') 100%);
  transition: opacity 0.15s, transform 0.1s;
}

.login-btn:hover:not(:disabled) {
  @apply opacity-90 -translate-y-px;
}

.login-btn:active:not(:disabled) {
  @apply translate-y-0;
}

.login-btn:disabled {
  @apply opacity-65 cursor-not-allowed;
}
</style>
