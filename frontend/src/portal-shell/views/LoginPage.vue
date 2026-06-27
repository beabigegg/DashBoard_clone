<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
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
const canvasRef = ref(null);

// ── Particle canvas ──────────────────────────────────────────────────────────
let rafId = null;
let particles = [];
const mouse = { x: -9999, y: -9999 };
const N = 55;
const CONNECT = 120;
const ATTRACT_R = 140;

function mkP(w, h) {
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.32,
    vy: (Math.random() - 0.5) * 0.32,
    r: Math.random() * 1.8 + 0.8,
    a: Math.random() * 0.28 + 0.1,
  };
}

function initCanvas() {
  const c = canvasRef.value;
  if (!c) return;
  c.width = window.innerWidth;
  c.height = window.innerHeight;
  particles = Array.from({ length: N }, () => mkP(c.width, c.height));
}

function frame() {
  const c = canvasRef.value;
  if (!c) return;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);

  // Subtle mouse bloom on light bg
  if (mouse.x > 0 && mouse.x < W) {
    const g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 120);
    g.addColorStop(0, 'rgba(0,128,200,0.055)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  for (const p of particles) {
    const dx = mouse.x - p.x, dy = mouse.y - p.y;
    const d = Math.hypot(dx, dy);
    if (d < ATTRACT_R && d > 0) {
      const f = ((ATTRACT_R - d) / ATTRACT_R) * 0.00035;
      p.vx += dx * f; p.vy += dy * f;
    }
    p.vx *= 0.984; p.vy *= 0.984;
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
    if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;

    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0,128,200,${p.a})`;
    ctx.fill();
  }

  // Connection lines — brand blue, very subtle on light bg
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const d = Math.hypot(particles[i].x - particles[j].x, particles[i].y - particles[j].y);
      if (d < CONNECT) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(0,128,200,${0.1 * (1 - d / CONNECT)})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }
    }
  }
  rafId = requestAnimationFrame(frame);
}

function onResize() { initCanvas(); }
function onMM(e) { mouse.x = e.clientX; mouse.y = e.clientY; }

onMounted(() => {
  initCanvas();
  frame();
  window.addEventListener('resize', onResize);
  window.addEventListener('mousemove', onMM);
});
onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId);
  window.removeEventListener('resize', onResize);
  window.removeEventListener('mousemove', onMM);
});

// ── Auth ─────────────────────────────────────────────────────────────────────
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
      if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//')) next = '/';
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
  <div class="lp">
    <!-- Particle canvas -->
    <canvas ref="canvasRef" class="lp-canvas" />
    <!-- Gradient background -->
    <div class="lp-bg" />
    <!-- Subtle dot grid -->
    <div class="lp-grid" />
    <!-- Ambient orbs -->
    <div class="lp-orb lp-orb--a" />
    <div class="lp-orb lp-orb--b" />
    <div class="lp-orb lp-orb--c" />

    <!-- ── Card ── -->
    <div class="lp-card">
      <!-- Top accent bar matching site nav -->
      <div class="lp-card-bar" />

      <!-- ── Logo / branding ── -->
      <div class="lp-head">
        <div class="lp-logo">
          <div class="lp-logo-ring" />
          <div class="lp-logo-core">
            <svg class="lp-logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1.2" />
              <rect x="14" y="3" width="7" height="7" rx="1.2" />
              <rect x="3" y="14" width="7" height="7" rx="1.2" />
              <path d="M17.5 14v7M14 17.5h7" />
            </svg>
          </div>
        </div>
        <h1 class="lp-title">MES 報表管理平台</h1>
        <p class="lp-sub">請使用員工帳號登入</p>
      </div>

      <!-- ── Divider ── -->
      <div class="lp-divider" />

      <!-- ── Form ── -->
      <form class="lp-form" @submit.prevent="handleSubmit">

        <!-- Username -->
        <div class="lp-field">
          <label for="username" class="lp-label">帳號（工號）</label>
          <div class="lp-wrap" :class="{ focused: usernameFocused }">
            <svg class="lp-icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 10a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H3z" />
            </svg>
            <input
              id="username"
              v-model="username"
              type="text"
              placeholder="請輸入工號"
              autocomplete="username"
              autofocus
              :disabled="loading"
              class="lp-input"
              @focus="usernameFocused = true"
              @blur="usernameFocused = false"
            />
          </div>
        </div>

        <!-- Password -->
        <div class="lp-field">
          <label for="password" class="lp-label">密碼</label>
          <div class="lp-wrap" :class="{ focused: passwordFocused }">
            <svg class="lp-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd" />
            </svg>
            <input
              id="password"
              v-model="password"
              type="password"
              placeholder="請輸入密碼"
              autocomplete="current-password"
              :disabled="loading"
              class="lp-input"
              @focus="passwordFocused = true"
              @blur="passwordFocused = false"
            />
          </div>
        </div>

        <!-- Error -->
        <Transition name="lp-err">
          <div v-if="errorMsg" class="lp-error" role="alert">
            <svg class="lp-err-icon shrink-0" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            {{ errorMsg }}
          </div>
        </Transition>

        <!-- Submit -->
        <button type="submit" class="lp-btn" :disabled="loading">
          <span class="lp-btn-sheen" />
          <svg v-if="loading" class="lp-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round" />
          </svg>
          <span class="lp-btn-text">{{ loading ? '登入中…' : '登入' }}</span>
          <svg v-if="!loading" class="lp-btn-arr" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </form>

      <!-- Footer -->
      <p class="lp-footer">Panjit Intl. · Manufacturing Execution System</p>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════ */
.lp {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.lp-canvas {
  position: absolute;
  inset: 0;
  z-index: 0;
}

/* Light gradient — brand palette */
.lp-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    linear-gradient(145deg,
      theme('colors.brand.50') 0%,
      theme('colors.surface.app') 45%,
      theme('colors.surface.muted') 100%);
}

/* Dot grid — very subtle */
.lp-grid {
  position: absolute;
  inset: 0;
  z-index: 1;
  background-image:
    radial-gradient(circle, rgba(0,128,200,0.15) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: radial-gradient(ellipse 85% 80% at 50% 50%, black 30%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 85% 80% at 50% 50%, black 30%, transparent 80%);
  opacity: 0.55;
}

/* Ambient glow orbs */
.lp-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  z-index: 0;
  animation: orb-drift 22s ease-in-out infinite;
}
.lp-orb--a {
  width: 500px; height: 500px;
  top: -180px; left: -140px;
  background: radial-gradient(circle, rgba(0,128,200,0.12) 0%, transparent 70%);
}
.lp-orb--b {
  width: 420px; height: 420px;
  bottom: -150px; right: -120px;
  background: radial-gradient(circle, rgba(0,163,224,0.1) 0%, transparent 70%);
  animation-delay: -9s;
}
.lp-orb--c {
  width: 300px; height: 300px;
  top: 35%; left: 62%;
  background: radial-gradient(circle, rgba(0,128,200,0.07) 0%, transparent 70%);
  animation-delay: -16s;
  filter: blur(50px);
}

@keyframes orb-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(22px, -16px) scale(1.06); }
  66% { transform: translate(-16px, 11px) scale(0.95); }
}

/* ═══════════════════════════════════════════════════
   Card
═══════════════════════════════════════════════════ */
.lp-card {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 408px;
  margin: 0 16px;
  padding: 36px 34px 28px;
  border-radius: 16px;
  background: theme('colors.surface.card');
  border: 1px solid theme('colors.stroke.panel');
  box-shadow:
    0 4px 6px rgba(0,0,0,0.04),
    0 20px 48px rgba(0,128,200,0.1),
    0 8px 24px rgba(0,0,0,0.06);
  animation: card-rise 0.65s cubic-bezier(0.16, 1, 0.3, 1) both;
  overflow: hidden;
}

@keyframes card-rise {
  from { opacity: 0; transform: translateY(20px) scale(0.974); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* Top bar — mirrors the site nav colour */
.lp-card-bar {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(
    90deg,
    theme('colors.brand.800') 0%,
    theme('colors.brand.500') 55%,
    theme('colors.accent.500') 100%
  );
}

/* ═══════════════════════════════════════════════════
   Logo / branding
═══════════════════════════════════════════════════ */
.lp-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 24px;
  padding-top: 8px;
}

.lp-logo {
  position: relative;
  width: 68px; height: 68px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}

/* Pulsing ring — brand.100 */
.lp-logo-ring {
  position: absolute;
  inset: -8px;
  border-radius: 20px;
  border: 2px solid theme('colors.brand.100');
  animation: logo-ring 2.6s ease-in-out infinite;
}

@keyframes logo-ring {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.06); opacity: 1; box-shadow: 0 0 0 6px rgba(0,128,200,0.06); }
}

/* Logo square — brand gradient matching nav */
.lp-logo-core {
  position: relative;
  z-index: 1;
  width: 56px; height: 56px;
  border-radius: 14px;
  background: linear-gradient(140deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 6px 20px rgba(0,128,200,0.35),
    0 2px 6px rgba(0,0,0,0.12);
}

.lp-logo-icon {
  width: 26px; height: 26px;
  color: rgba(255,255,255,0.96);
}

.lp-title {
  font-size: 1.2rem;
  font-weight: 700;
  color: theme('colors.text.primary');
  letter-spacing: 0.01em;
  margin: 0 0 5px;
}

.lp-sub {
  font-size: 0.8125rem;
  color: theme('colors.text.secondary');
  margin: 0;
}

/* ═══════════════════════════════════════════════════
   Divider
═══════════════════════════════════════════════════ */
.lp-divider {
  height: 1px;
  background: theme('colors.stroke.soft');
  margin: 0 0 24px;
}

/* ═══════════════════════════════════════════════════
   Form
═══════════════════════════════════════════════════ */
.lp-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lp-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lp-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: theme('colors.text.secondary');
  letter-spacing: 0.03em;
}

.lp-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 13px;
  border-radius: 10px;
  background: theme('colors.surface.muted');
  border: 1.5px solid theme('colors.stroke.input');
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.lp-wrap.focused {
  background: theme('colors.surface.card');
  border-color: theme('colors.brand.500');
  box-shadow: 0 0 0 3px rgba(0,128,200,0.1);
}

.lp-icon {
  width: 15px; height: 15px;
  flex-shrink: 0;
  color: theme('colors.text.muted');
  transition: color 0.2s;
}

.lp-wrap.focused .lp-icon {
  color: theme('colors.brand.500');
}

.lp-input {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  font-size: 0.9rem;
  color: theme('colors.text.primary');
}

.lp-input::placeholder {
  color: theme('colors.token.h9ca3af');
}

.lp-input:disabled {
  color: theme('colors.token.h94a3b8');
}

/* Error */
.lp-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 13px;
  border-radius: 8px;
  font-size: 0.8125rem;
  color: theme('colors.state.danger');
  background: theme('colors.token.hfee2e2');
  border: 1px solid theme('colors.token.hfecaca');
}

.lp-err-icon { width: 15px; height: 15px; margin-top: 1px; }

.lp-err-enter-active, .lp-err-leave-active { transition: all 0.22s ease; }
.lp-err-enter-from, .lp-err-leave-to { opacity: 0; transform: translateY(-5px); }

/* ═══════════════════════════════════════════════════
   Button
═══════════════════════════════════════════════════ */
.lp-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  overflow: hidden;
  margin-top: 4px;
  background: theme('colors.brand.500');
  box-shadow: 0 4px 16px rgba(0,128,200,0.3), 0 1px 4px rgba(0,0,0,0.1);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s, background 0.2s;
}

.lp-btn:hover:not(:disabled) {
  background: theme('colors.brand.600');
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(0,128,200,0.38), 0 2px 6px rgba(0,0,0,0.1);
}

.lp-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(0,128,200,0.25);
}

.lp-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* Sheen sweep on hover */
.lp-btn-sheen {
  position: absolute;
  top: 0; left: -90%;
  width: 50%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
  transform: skewX(-18deg);
  pointer-events: none;
}
.lp-btn:hover:not(:disabled) .lp-btn-sheen {
  left: 180%;
  transition: left 0.55s ease;
}

.lp-btn-text {
  position: relative;
  z-index: 1;
  font-size: 0.9rem;
  font-weight: 600;
  color: rgba(255,255,255,1);
  letter-spacing: 0.02em;
}

.lp-btn-arr {
  position: relative;
  z-index: 1;
  width: 15px; height: 15px;
  color: rgba(255,255,255,0.88);
  transition: transform 0.2s;
}

.lp-btn:hover:not(:disabled) .lp-btn-arr {
  transform: translateX(2px);
}

.lp-spinner {
  position: relative;
  z-index: 1;
  width: 17px; height: 17px;
  color: rgba(255,255,255,0.9);
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ═══════════════════════════════════════════════════
   Footer
═══════════════════════════════════════════════════ */
.lp-footer {
  margin: 20px 0 0;
  text-align: center;
  font-size: 0.7rem;
  color: theme('colors.token.h94a3b8');
  letter-spacing: 0.04em;
}

/* ═══════════════════════════════════════════════════
   Reduced motion
═══════════════════════════════════════════════════ */
@media (prefers-reduced-motion: reduce) {
  .lp-card { animation: none; }
  .lp-orb, .lp-logo-ring { animation: none; }
  .lp-btn-sheen { display: none; }
}
</style>
