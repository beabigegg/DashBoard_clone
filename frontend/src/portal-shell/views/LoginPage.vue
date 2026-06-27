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
const N = 88;
const CONNECT = 110;
const ATTRACT_R = 170;

function mkP(w, h) {
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.38,
    vy: (Math.random() - 0.5) * 0.38,
    r: Math.random() * 1.3 + 0.45,
    a: Math.random() * 0.45 + 0.18,
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

  // Mouse bloom
  const g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 150);
  g.addColorStop(0, 'rgba(0,200,255,0.075)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  for (const p of particles) {
    const dx = mouse.x - p.x, dy = mouse.y - p.y;
    const d = Math.hypot(dx, dy);
    if (d < ATTRACT_R && d > 0) {
      const f = ((ATTRACT_R - d) / ATTRACT_R) * 0.00042;
      p.vx += dx * f; p.vy += dy * f;
    }
    p.vx *= 0.981; p.vy *= 0.981;
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
    if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0,200,255,${p.a})`;
    ctx.fill();
  }

  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const d = Math.hypot(particles[i].x - particles[j].x, particles[i].y - particles[j].y);
      if (d < CONNECT) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(0,175,255,${0.18 * (1 - d / CONNECT)})`;
        ctx.lineWidth = 0.5;
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
    <!-- Layer: canvas particles -->
    <canvas ref="canvasRef" class="lp-canvas" />
    <!-- Layer: base gradient -->
    <div class="lp-bg" />
    <!-- Layer: grid pattern -->
    <div class="lp-grid" />
    <!-- Layer: atmospheric orbs -->
    <div class="lp-orb lp-orb--a" />
    <div class="lp-orb lp-orb--b" />
    <!-- Layer: periodic scan sweep -->
    <div class="lp-sweep" />

    <!-- ── Card ── -->
    <div class="lp-card">
      <!-- Corner HUD brackets -->
      <span class="hud hud--tl" /><span class="hud hud--tr" />
      <span class="hud hud--bl" /><span class="hud hud--br" />
      <!-- Top luminous bar -->
      <div class="lp-topbar" />

      <!-- ── Header ── -->
      <div class="lp-head">
        <div class="lp-logo">
          <div class="logo-halo" />
          <div class="logo-halo logo-halo--2" />
          <div class="logo-core">
            <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1.2" />
              <rect x="14" y="3" width="7" height="7" rx="1.2" />
              <rect x="3" y="14" width="7" height="7" rx="1.2" />
              <path d="M17.5 14v7M14 17.5h7" />
            </svg>
          </div>
        </div>
        <div class="lp-sys-tag">MES · INTELLIGENT REPORTING SYSTEM</div>
        <h1 class="lp-title">報表管理平台</h1>
        <p class="lp-sub">請使用員工帳號登入系統</p>
      </div>

      <!-- ── Form ── -->
      <form class="lp-form" @submit.prevent="handleSubmit">

        <!-- Username -->
        <div class="lp-field">
          <label for="username" class="lp-label">
            <span class="lp-badge">01</span>帳號 · EMPLOYEE ID
          </label>
          <div class="lp-wrap" :class="{ focused: usernameFocused }">
            <svg class="lp-icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 10a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H3z" />
            </svg>
            <input
              id="username"
              v-model="username"
              type="text"
              placeholder="輸入工號"
              autocomplete="username"
              autofocus
              :disabled="loading"
              class="lp-input"
              @focus="usernameFocused = true"
              @blur="usernameFocused = false"
            />
            <div class="lp-focus-line" />
          </div>
        </div>

        <!-- Password -->
        <div class="lp-field">
          <label for="password" class="lp-label">
            <span class="lp-badge">02</span>密碼 · PASSWORD
          </label>
          <div class="lp-wrap" :class="{ focused: passwordFocused }">
            <svg class="lp-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd" />
            </svg>
            <input
              id="password"
              v-model="password"
              type="password"
              placeholder="輸入密碼"
              autocomplete="current-password"
              :disabled="loading"
              class="lp-input"
              @focus="passwordFocused = true"
              @blur="passwordFocused = false"
            />
            <div class="lp-focus-line" />
          </div>
        </div>

        <!-- Error message -->
        <Transition name="lp-err">
          <div v-if="errorMsg" class="lp-error" role="alert">
            <svg class="shrink-0 lp-err-icon" viewBox="0 0 20 20" fill="currentColor">
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
          <span class="lp-btn-text">{{ loading ? '驗證中…' : '登 入 系 統' }}</span>
          <svg v-if="!loading" class="lp-btn-arr" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </form>

      <!-- Footer -->
      <div class="lp-footer">
        <div class="lp-footer-rule" />
        <span>PANJIT INTL. · MES v3</span>
        <div class="lp-footer-rule" />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════
   Page shell
═══════════════════════════════════════════════════ */
.lp {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: rgb(2, 9, 18);
}

.lp-canvas {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.lp-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: radial-gradient(ellipse 110% 90% at 50% 42%, rgb(6, 19, 38) 0%, rgb(2, 9, 18) 65%);
}

/* Grid */
.lp-grid {
  position: absolute;
  inset: 0;
  z-index: 1;
  background-image:
    linear-gradient(rgba(0, 180, 255, 0.038) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 180, 255, 0.038) 1px, transparent 1px);
  background-size: 58px 58px;
  mask-image: radial-gradient(ellipse 88% 78% at 50% 50%, black 25%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 88% 78% at 50% 50%, black 25%, transparent 80%);
}

/* Atmospheric orbs */
.lp-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  z-index: 0;
  animation: orb-drift 26s ease-in-out infinite;
}
.lp-orb--a {
  width: 650px; height: 650px;
  top: -230px; left: -200px;
  background: radial-gradient(circle, rgba(0, 70, 150, 0.42) 0%, transparent 70%);
}
.lp-orb--b {
  width: 520px; height: 520px;
  bottom: -180px; right: -160px;
  background: radial-gradient(circle, rgba(0, 100, 180, 0.32) 0%, transparent 70%);
  animation-delay: -11s;
}

@keyframes orb-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(28px, -20px) scale(1.06); }
  66% { transform: translate(-20px, 14px) scale(0.94); }
}

/* Periodic scan sweep */
.lp-sweep {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  overflow: hidden;
}
.lp-sweep::after {
  content: '';
  position: absolute;
  left: 0; right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 8%,
    rgba(0, 200, 255, 0.055) 35%,
    rgba(0, 220, 255, 0.08) 50%,
    rgba(0, 200, 255, 0.055) 65%,
    transparent 92%
  );
  animation: sweep 7s linear infinite;
}
@keyframes sweep {
  from { top: -2px; }
  to { top: 100vh; }
}

/* ═══════════════════════════════════════════════════
   Card
═══════════════════════════════════════════════════ */
.lp-card {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 420px;
  margin: 0 16px;
  padding: 38px 34px 30px;
  border-radius: 20px;
  background: rgba(6, 14, 36, 0.84);
  backdrop-filter: blur(28px) saturate(1.3);
  -webkit-backdrop-filter: blur(28px) saturate(1.3);
  border: 1px solid rgba(0, 195, 255, 0.14);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.028),
    0 36px 72px rgba(0, 0, 0, 0.65),
    0 0 100px -10px rgba(0, 130, 220, 0.22);
  animation: card-rise 0.75s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes card-rise {
  from { opacity: 0; transform: translateY(22px) scale(0.968); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* HUD corner brackets */
.hud {
  position: absolute;
  width: 14px;
  height: 14px;
  border-color: rgba(0, 210, 255, 0.44);
  border-style: solid;
}
.hud--tl { top: 11px; left: 11px; border-width: 2px 0 0 2px; border-radius: 3px 0 0 0; }
.hud--tr { top: 11px; right: 11px; border-width: 2px 2px 0 0; border-radius: 0 3px 0 0; }
.hud--bl { bottom: 11px; left: 11px; border-width: 0 0 2px 2px; border-radius: 0 0 0 3px; }
.hud--br { bottom: 11px; right: 11px; border-width: 0 2px 2px 0; border-radius: 0 0 3px 0; }

/* Luminous top edge */
.lp-topbar {
  position: absolute;
  top: 0; left: 16%; right: 16%;
  height: 1px;
  border-radius: 1px;
  background: linear-gradient(90deg, transparent, rgba(0, 210, 255, 0.75), transparent);
}

/* ═══════════════════════════════════════════════════
   Header / Logo
═══════════════════════════════════════════════════ */
.lp-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 30px;
}

.lp-logo {
  position: relative;
  width: 74px; height: 74px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}

.logo-halo {
  position: absolute;
  inset: -9px;
  border-radius: 22px;
  border: 1.5px solid rgba(0, 210, 255, 0.22);
  animation: halo 2.9s ease-in-out infinite;
}
.logo-halo--2 {
  inset: -17px;
  border-color: rgba(0, 210, 255, 0.1);
  animation-delay: -1.45s;
}

@keyframes halo {
  0%, 100% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.055); opacity: 0.9; box-shadow: 0 0 14px 1px rgba(0, 210, 255, 0.14); }
}

.logo-core {
  position: relative;
  z-index: 1;
  width: 58px; height: 58px;
  border-radius: 16px;
  background: linear-gradient(148deg, rgb(7, 24, 48) 0%, rgb(10, 36, 72) 55%, rgb(13, 53, 104) 100%);
  border: 1px solid rgba(0, 210, 255, 0.38);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 0 22px rgba(0, 210, 255, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    inset 0 -1px 0 rgba(0, 0, 0, 0.3);
}

.logo-icon {
  width: 28px; height: 28px;
  color: rgb(24, 212, 255);
  filter: drop-shadow(0 0 6px rgba(0, 210, 255, 0.55));
}

.lp-sys-tag {
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.2em;
  color: rgba(0, 200, 255, 0.46);
  text-transform: uppercase;
  margin-bottom: 9px;
}

.lp-title {
  font-size: 1.28rem;
  font-weight: 700;
  color: rgba(215, 238, 255, 0.94);
  letter-spacing: 0.05em;
  margin: 0 0 5px;
}

.lp-sub {
  font-size: 0.8rem;
  color: rgba(110, 160, 210, 0.65);
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
  gap: 7px;
}

.lp-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.13em;
  color: rgba(95, 155, 210, 0.72);
  text-transform: uppercase;
  user-select: none;
}

.lp-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px; height: 16px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  background: rgba(0, 200, 255, 0.07);
  border: 1px solid rgba(0, 200, 255, 0.22);
  color: rgba(0, 200, 255, 0.6);
}

.lp-wrap {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 11px;
  background: rgba(8, 20, 50, 0.68);
  border: 1.5px solid rgba(40, 90, 155, 0.28);
  transition: border-color 0.22s, background 0.22s, box-shadow 0.22s;
  overflow: hidden;
}

.lp-wrap.focused {
  background: rgba(5, 16, 42, 0.9);
  border-color: rgba(0, 210, 255, 0.58);
  box-shadow: 0 0 0 3px rgba(0, 210, 255, 0.1), 0 0 18px rgba(0, 200, 255, 0.07);
}

/* Bottom glow line on focus */
.lp-focus-line {
  position: absolute;
  bottom: 0; left: 12%; right: 12%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0, 210, 255, 0.7), transparent);
  opacity: 0;
  transform: scaleX(0.4);
  transition: opacity 0.22s, transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.lp-wrap.focused .lp-focus-line {
  opacity: 1;
  transform: scaleX(1);
}

.lp-icon {
  width: 16px; height: 16px;
  flex-shrink: 0;
  color: rgba(80, 135, 200, 0.5);
  transition: color 0.2s;
}

.lp-wrap.focused .lp-icon {
  color: rgba(0, 210, 255, 0.72);
}

.lp-input {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  font-size: 0.895rem;
  color: rgba(210, 235, 255, 0.9);
}

.lp-input::placeholder {
  color: rgba(75, 120, 170, 0.42);
}

.lp-input:disabled {
  color: rgba(90, 130, 175, 0.35);
}

/* Error */
.lp-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 13px;
  border-radius: 10px;
  font-size: 0.8rem;
  color: rgb(255, 112, 112);
  background: rgba(255, 60, 60, 0.08);
  border: 1px solid rgba(255, 60, 60, 0.22);
}

.lp-err-icon { width: 15px; height: 15px; }

.lp-err-enter-active, .lp-err-leave-active { transition: all 0.24s ease; }
.lp-err-enter-from, .lp-err-leave-to { opacity: 0; transform: translateY(-6px); }

/* ═══════════════════════════════════════════════════
   Button
═══════════════════════════════════════════════════ */
.lp-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 13px 20px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  overflow: hidden;
  margin-top: 4px;
  background: linear-gradient(135deg, theme('colors.brand.600') 0%, theme('colors.brand.500') 52%, theme('colors.accent.500') 100%);
  box-shadow:
    0 4px 22px rgba(0, 128, 200, 0.32),
    0 0 0 1px rgba(0, 200, 255, 0.22);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s;
}

.lp-btn:hover:not(:disabled) {
  transform: translateY(-1.5px);
  box-shadow:
    0 8px 30px rgba(0, 128, 200, 0.48),
    0 0 0 1px rgba(0, 210, 255, 0.4);
}

.lp-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 3px 12px rgba(0, 128, 200, 0.28), 0 0 0 1px rgba(0, 200, 255, 0.2);
}

.lp-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Sheen sweep — transition approach re-plays on every hover */
.lp-btn-sheen {
  position: absolute;
  top: 0; left: -90%;
  width: 55%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.16), transparent);
  transform: skewX(-18deg);
  pointer-events: none;
  /* no transition here = instant reset on mouse-out */
}
.lp-btn:hover:not(:disabled) .lp-btn-sheen {
  left: 170%;
  transition: left 0.58s ease;
}

.lp-btn-text {
  position: relative;
  z-index: 1;
  font-size: 0.9rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 1);
  letter-spacing: 0.08em;
}

.lp-btn-arr {
  position: relative;
  z-index: 1;
  width: 16px; height: 16px;
  color: rgba(255, 255, 255, 0.82);
}

.lp-spinner {
  position: relative;
  z-index: 1;
  width: 18px; height: 18px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ═══════════════════════════════════════════════════
   Footer
═══════════════════════════════════════════════════ */
.lp-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 26px;
  color: rgba(70, 115, 165, 0.42);
  font-size: 8.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.lp-footer-rule {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0, 175, 255, 0.1), transparent);
}

/* ═══════════════════════════════════════════════════
   Reduced motion
═══════════════════════════════════════════════════ */
@media (prefers-reduced-motion: reduce) {
  .lp-card { animation: none; }
  .lp-orb, .logo-halo { animation: none; }
  .lp-sweep::after { animation: none; }
  .lp-btn-sheen { display: none; }
}
</style>
