import { createApp } from 'vue';

import '../wip-shared/styles.css';
import '../styles/tailwind.css';
import './style.css';
import App from './App.vue';
import { restoreUrlState } from '../core/shell-navigation.js';

restoreUrlState();
createApp(App).mount('#app');
