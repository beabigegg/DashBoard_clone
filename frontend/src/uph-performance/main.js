import { createApp } from 'vue';

import App from './App.vue';
// UPH表現 does not reuse resource-shared's `:is(.theme-X, …)` grouped component
// styles (css-contract §Known Global Rule Interactions) — it replicates its own
// layout rules locally under `.theme-uph-performance`, mirroring admin-pages /
// admin-dashboard / material-consumption, so it depends only on the global
// tailwind base/components layer plus its own scoped style.css.
import '../styles/tailwind.css';
import './style.css';
import { restoreUrlState } from '../core/shell-navigation';

restoreUrlState();
createApp(App).mount('#app');
