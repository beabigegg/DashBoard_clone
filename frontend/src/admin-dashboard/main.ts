import { createApp } from 'vue';

// @ts-expect-error admin-dashboard App.vue not yet migrated to lang="ts" (Phase 3 pending)
import App from './App.vue';
import '../styles/tailwind.css';
import './style.css';

createApp(App).mount('#app');
