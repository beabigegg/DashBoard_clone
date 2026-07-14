import { createApp } from 'vue';

import App from './App.vue';
import '../styles/tailwind.css';
import '../resource-shared/styles.css';
import './style.css';
import { restoreUrlState } from '../core/shell-navigation';

restoreUrlState();
createApp(App).mount('#app');
