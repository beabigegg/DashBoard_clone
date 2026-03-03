import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => ({
  base: '/static/dist/',
  plugins: [vue()],
  publicDir: false,
  build: {
    outDir: '../src/mes_dashboard/static/dist',
    emptyOutDir: false,
    sourcemap: mode !== 'production',
    rollupOptions: {
      input: {
        portal: resolve(__dirname, 'src/portal/main.js'),
        'portal-shell': resolve(__dirname, 'src/portal-shell/index.html'),
        'wip-overview': resolve(__dirname, 'src/wip-overview/index.html'),
        'wip-detail': resolve(__dirname, 'src/wip-detail/index.html'),
        'hold-detail': resolve(__dirname, 'src/hold-detail/index.html'),
        'hold-overview': resolve(__dirname, 'src/hold-overview/index.html'),
        'hold-history': resolve(__dirname, 'src/hold-history/index.html'),
        'reject-history': resolve(__dirname, 'src/reject-history/index.html'),
        'resource-status': resolve(__dirname, 'src/resource-status/index.html'),
        'resource-history': resolve(__dirname, 'src/resource-history/index.html'),
        'job-query': resolve(__dirname, 'src/job-query/main.js'),
        'excel-query': resolve(__dirname, 'src/excel-query/main.js'),
        tables: resolve(__dirname, 'src/tables/index.html'),
        'query-tool': resolve(__dirname, 'src/query-tool/main.js'),
        'qc-gate': resolve(__dirname, 'src/qc-gate/index.html'),
        'mid-section-defect': resolve(__dirname, 'src/mid-section-defect/index.html'),
        'admin-performance': resolve(__dirname, 'src/admin-performance/index.html'),
        'material-trace': resolve(__dirname, 'src/material-trace/index.html')
      },
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
        }
      }
    }
  }
}));
