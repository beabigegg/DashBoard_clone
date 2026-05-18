<script setup>
defineProps({
  departments: { type: Array, default: () => [] },
});

function formatDuration(sec) {
  if (sec == null) return '-';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}
</script>

<template>
  <div>
    <table v-if="departments.length > 0" class="mini-table">
      <thead>
        <tr>
          <th>部門</th>
          <th class="text-right">使用者</th>
          <th class="text-right">登入次數</th>
          <th class="text-right">平均時長</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in departments" :key="d.department">
          <td>{{ d.department }}</td>
          <td class="text-right">{{ d.unique_users }}</td>
          <td class="text-right">{{ d.total_sessions }}</td>
          <td class="text-right">{{ formatDuration(d.avg_duration_sec) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-text">尚無部門資料</div>
  </div>
</template>
