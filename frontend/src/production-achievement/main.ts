import { createApp } from 'vue';

import App from './App.vue';
import './style.css';
import { restoreUrlState } from '../core/shell-navigation';

restoreUrlState();
createApp(App).mount('#app');
