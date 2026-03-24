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
const usernameFocused = ref(false);
const passwordFocused = ref(false);

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
  <div class="login-page">
    <!-- Animated background -->
    <div class="login-bg-layer" />
    <div class="login-orb login-orb--1" />
    <div class="login-orb login-orb--2" />
    <div class="login-orb login-orb--3" />

    <!-- Card -->
    <div class="login-card">
      <!-- Logo area -->
      <div class="flex flex-col items-center mb-8">
        <div class="login-logo-ring">
          <svg class="w-7 h-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <path d="M17.5 14v7M14 17.5h7" />
          </svg>
        </div>
        <h1 class="text-[1.35rem] font-bold text-text-primary tracking-tight mt-4">MES 報表系統</h1>
        <p class="text-text-secondary text-sm mt-1">請使用員工帳號登入</p>
      </div>

      <form class="flex flex-col gap-5" @submit.prevent="handleSubmit">
        <!-- Username -->
        <div class="login-field-group">
          <label for="username" class="login-label">帳號（工號）</label>
          <div class="login-input-wrap" :class="{ 'login-input-wrap--focus': usernameFocused }">
            <svg class="login-input-icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 10a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H3z" />
            </svg>
            <input
              id="username"
              v-model="username"
              type="text"
              placeholder="請輸入工號"
              autocomplete="username"
              :disabled="loading"
              class="login-input"
              @focus="usernameFocused = true"
              @blur="usernameFocused = false"
            />
          </div>
        </div>

        <!-- Password -->
        <div class="login-field-group">
          <label for="password" class="login-label">密碼</label>
          <div class="login-input-wrap" :class="{ 'login-input-wrap--focus': passwordFocused }">
            <svg class="login-input-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd" />
            </svg>
            <input
              id="password"
              v-model="password"
              type="password"
              placeholder="請輸入密碼"
              autocomplete="current-password"
              :disabled="loading"
              class="login-input"
              @focus="passwordFocused = true"
              @blur="passwordFocused = false"
            />
          </div>
        </div>

        <!-- Error -->
        <Transition name="login-error">
          <div v-if="errorMsg" class="login-error" role="alert">
            <svg class="w-4 h-4 shrink-0 mt-px" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            {{ errorMsg }}
          </div>
        </Transition>

        <!-- Submit -->
        <button type="submit" class="login-btn" :disabled="loading">
          <svg v-if="loading" class="login-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round" />
          </svg>
          <span>{{ loading ? '登入中…' : '登入' }}</span>
          <svg v-if="!loading" class="w-4 h-4 ml-1 transition-transform group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* ── Page layout ── */
.login-page {
  @apply min-h-screen flex items-center justify-center relative overflow-hidden;
}

.login-bg-layer {
  @apply absolute inset-0;
  background: linear-gradient(
    135deg,
    theme('colors.token.h0f172a') 0%,
    theme('colors.token.h1e293b') 50%,
    theme('colors.token.h0f172a') 100%
  );
}

/* ── Floating orbs ── */
.login-orb {
  @apply absolute rounded-full opacity-30 blur-3xl;
  animation: orb-float 20s ease-in-out infinite;
}

.login-orb--1 {
  @apply w-[500px] h-[500px] -top-40 -left-24;
  background: radial-gradient(circle, theme('colors.brand.500') 0%, transparent 70%);
}

.login-orb--2 {
  @apply w-[400px] h-[400px] -bottom-32 -right-16;
  background: radial-gradient(circle, theme('colors.accent.500') 0%, transparent 70%);
  animation-delay: -7s;
}

.login-orb--3 {
  @apply w-[300px] h-[300px] top-1/3 right-1/4;
  background: radial-gradient(circle, theme('colors.brand.600') 0%, transparent 70%);
  animation-delay: -13s;
  opacity: 0.15;
}

@keyframes orb-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -20px) scale(1.05); }
  66% { transform: translate(-20px, 15px) scale(0.95); }
}

/* ── Card ── */
.login-card {
  @apply relative w-full max-w-[420px] mx-4 p-10 rounded-2xl;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px) saturate(1.6);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.15),
    0 25px 50px -12px rgba(0, 0, 0, 0.4),
    0 0 80px -20px rgba(0, 128, 200, 0.15);
}

/* ── Logo ring ── */
.login-logo-ring {
  @apply w-14 h-14 rounded-2xl flex items-center justify-center;
  background: linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%);
  box-shadow: 0 8px 24px -4px rgba(0, 128, 200, 0.35);
}

/* ── Form fields ── */
.login-field-group {
  @apply flex flex-col gap-1.5;
}

.login-label {
  @apply text-xs font-semibold text-text-secondary uppercase tracking-wider;
}

.login-input-wrap {
  @apply flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border-2 border-transparent;
  background: theme('colors.surface.muted');
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.login-input-wrap--focus {
  background: white;
  border-color: theme('colors.brand.500');
  box-shadow: 0 0 0 4px rgba(0, 128, 200, 0.12);
}

.login-input-icon {
  @apply w-[18px] h-[18px] shrink-0 text-gray-400 transition-colors;
}

.login-input-wrap--focus .login-input-icon {
  color: theme('colors.brand.500');
}

.login-input {
  @apply w-full bg-transparent border-0 outline-none text-[0.9375rem] text-text-primary placeholder:text-gray-400;
}

.login-input:disabled {
  @apply text-gray-400;
}

/* ── Error ── */
.login-error {
  @apply flex items-start gap-2 px-3.5 py-2.5 rounded-xl text-red-600 text-sm;
  background: rgba(239, 68, 68, 0.08);
}

.login-error-enter-active,
.login-error-leave-active {
  transition: all 0.25s ease;
}
.login-error-enter-from,
.login-error-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ── Button ── */
.login-btn {
  @apply relative flex items-center justify-center gap-2 py-3.5 text-white border-0 rounded-xl text-[0.9375rem] font-semibold cursor-pointer mt-1;
  background: theme('colors.brand.500');
  box-shadow: 0 4px 16px -2px rgba(0, 128, 200, 0.35);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.login-btn:hover:not(:disabled) {
  background: theme('colors.brand.600');
  box-shadow: 0 8px 24px -4px rgba(0, 128, 200, 0.4);
  transform: translateY(-1px);
}

.login-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 2px 8px -2px rgba(0, 128, 200, 0.35);
}

.login-btn:disabled {
  @apply opacity-60 cursor-not-allowed;
}

/* ── Spinner ── */
.login-spinner {
  @apply w-5 h-5;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
