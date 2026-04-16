import { createApp } from 'vue';

import App from './App.vue';
import '../resource-shared/styles.css';
import '../wip-shared/styles.css';
import './style.css';
import { restoreUrlState } from '../core/shell-navigation.js';

restoreUrlState();
createApp(App).mount('#app');
