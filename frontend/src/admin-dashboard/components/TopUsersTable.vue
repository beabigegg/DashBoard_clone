<script setup>
defineProps({
  users: { type: Array, default: () => [] },
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
    <table v-if="users.length > 0" class="mini-table">
      <thead>
        <tr>
          <th>使用者</th>
          <th>部門</th>
          <th class="text-right">登入次數</th>
          <th class="text-right">平均時長</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.username">
          <td>{{ u.display_name || u.username }}</td>
          <td>{{ u.department || '-' }}</td>
          <td class="text-right">{{ u.login_count }}</td>
          <td class="text-right">{{ formatDuration(u.avg_duration_sec) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-text">尚無使用者資料</div>
  </div>
</template>
