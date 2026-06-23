import { copyFileSync, existsSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import type { Plugin } from 'vite';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const FLASK_PORT = process.env['VITE_FLASK_PORT'] ?? '8080';
const DEV_PORT   = parseInt(process.env['VITE_DEV_PORT'] ?? '5173');
const OUT_DIR    = resolve(__dirname, '../src/mes_dashboard/static/dist');

// ── rollupOptions.input entries ───────────────────────────────────────────
// Keep this map in sync with any new pages added to the project.
// HTML entries are automatically copied to OUT_DIR/<name>.html after build.
const INPUT_MAP: Record<string, string> = {
  portal:                 resolve(__dirname, 'src/portal/main.js'),
  'portal-shell':         resolve(__dirname, 'src/portal-shell/index.html'),
  'wip-overview':         resolve(__dirname, 'src/wip-overview/index.html'),
  'wip-detail':           resolve(__dirname, 'src/wip-detail/index.html'),
  'hold-detail':          resolve(__dirname, 'src/hold-detail/index.html'),
  'hold-overview':        resolve(__dirname, 'src/hold-overview/index.html'),
  'hold-history':         resolve(__dirname, 'src/hold-history/index.html'),
  'reject-history':       resolve(__dirname, 'src/reject-history/index.html'),
  'resource-status':      resolve(__dirname, 'src/resource-status/index.html'),
  'resource-history':     resolve(__dirname, 'src/resource-history/index.html'),
  'job-query':            resolve(__dirname, 'src/job-query/main.js'),
  'production-history':   resolve(__dirname, 'src/production-history/index.html'),
  'query-tool':           resolve(__dirname, 'src/query-tool/main.js'),
  'qc-gate':              resolve(__dirname, 'src/qc-gate/index.html'),
  'mid-section-defect':   resolve(__dirname, 'src/mid-section-defect/index.html'),
  'admin-dashboard':      resolve(__dirname, 'src/admin-dashboard/index.html'),
  'admin-pages':          resolve(__dirname, 'src/admin-pages/index.html'),
  'material-trace':       resolve(__dirname, 'src/material-trace/index.html'),
  'yield-alert-center':   resolve(__dirname, 'src/yield-alert-center/index.html'),
  'anomaly-overview':     resolve(__dirname, 'src/anomaly-overview/index.html'),
  'material-consumption': resolve(__dirname, 'src/material-consumption/index.html'),
  'downtime-analysis':    resolve(__dirname, 'src/downtime-analysis/index.html'),
  'eap-alarm':            resolve(__dirname, 'src/eap-alarm/index.html'),
};

// After each bundle write (including --watch rebuilds), copy HTML entry points
// from OUT_DIR/src/<page>/index.html → OUT_DIR/<page>.html so Flask can serve them.
function copyHtmlPlugin(): Plugin {
  return {
    name: 'copy-html-to-dist-root',
    closeBundle() {
      for (const [name, srcPath] of Object.entries(INPUT_MAP)) {
        if (!srcPath.endsWith('index.html')) continue;
        const relFromRoot = relative(__dirname, srcPath); // e.g. src/wip-overview/index.html
        const builtPath   = join(OUT_DIR, relFromRoot);
        const destPath    = join(OUT_DIR, `${name}.html`);
        if (existsSync(builtPath)) {
          copyFileSync(builtPath, destPath);
        }
      }
    },
  };
}

export default defineConfig(({ mode }) => ({
  base: '/static/dist/',
  plugins: [vue(), copyHtmlPlugin()],
  publicDir: false,
  esbuild: {
    // production build 時移除所有 console.* 呼叫，避免洩漏除錯資訊
    drop: mode === 'production' ? ['console', 'debugger'] : [],
  },
  server: {
    port: DEV_PORT,
    proxy: {
      // 攔截一切請求；bypass 讓 Vite 自己處理 HMR 資產
      '^/': {
        target: `http://localhost:${FLASK_PORT}`,
        changeOrigin: true,
        ws: false,
        bypass(req) {
          const url = req.url ?? '';
          // Vite HMR 資產與模組不代理，其餘全轉 Flask
          if (
            url.startsWith('/static/dist/') ||
            url.startsWith('/@vite') ||
            url.startsWith('/@fs') ||
            url.startsWith('/node_modules')
          ) {
            return url;
          }
        },
      },
    },
  },
  build: {
    outDir: OUT_DIR,
    emptyOutDir: false,
    sourcemap: mode !== 'production',
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      input: INPUT_MAP,
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: '[name][extname]',
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/');
          if (!normalizedId.includes('node_modules')) {
            return;
          }
          if (
            normalizedId.includes('/node_modules/echarts/') ||
            normalizedId.includes('/node_modules/zrender/') ||
            normalizedId.includes('/node_modules/vue-echarts/')
          ) {
            return 'vendor-echarts';
          }
          if (
            normalizedId.includes('/node_modules/vue/') ||
            normalizedId.includes('/node_modules/@vue/')
          ) {
            return 'vendor-vue';
          }
          return 'vendor';
        },
      },
    },
  },
}));
