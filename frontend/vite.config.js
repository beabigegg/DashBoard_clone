import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig(({ mode }) => ({
  publicDir: false,
  build: {
    outDir: '../src/mes_dashboard/static/dist',
    emptyOutDir: false,
    sourcemap: mode !== 'production',
    rollupOptions: {
      input: {
        portal: resolve(__dirname, 'src/portal/main.js'),
        'wip-overview': resolve(__dirname, 'src/wip-overview/main.js'),
        'wip-detail': resolve(__dirname, 'src/wip-detail/main.js'),
        'hold-detail': resolve(__dirname, 'src/hold-detail/main.js'),
        'resource-status': resolve(__dirname, 'src/resource-status/main.js'),
        'resource-history': resolve(__dirname, 'src/resource-history/main.js'),
        'job-query': resolve(__dirname, 'src/job-query/main.js'),
        'excel-query': resolve(__dirname, 'src/excel-query/main.js'),
        tables: resolve(__dirname, 'src/tables/main.js'),
        'query-tool': resolve(__dirname, 'src/query-tool/main.js'),
        'tmtt-defect': resolve(__dirname, 'src/tmtt-defect/main.js')
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: '[name][extname]',
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return;
          }
          if (id.includes('echarts')) {
            return 'vendor-echarts';
          }
          return 'vendor';
        }
      }
    }
  }
}));
