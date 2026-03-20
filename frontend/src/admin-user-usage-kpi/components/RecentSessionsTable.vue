<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
});

function formatTime(iso) {
  if (!iso) return '-';
  return iso.replace('T', ' ').slice(0, 19);
}

function formatDuration(sec) {
  if (sec == null) return '-';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}
</script>

<template>
  <div>
    <table v-if="sessions.length > 0" class="mini-table">
      <thead>
        <tr>
          <th>使用者</th>
          <th>部門</th>
          <th>登入時間</th>
          <th class="text-right">時長</th>
          <th>狀態</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(s, i) in sessions" :key="i">
          <td>{{ s.display_name || s.username }}</td>
          <td>{{ s.department || '-' }}</td>
          <td>{{ formatTime(s.login_time) }}</td>
          <td class="text-right">{{ formatDuration(s.duration_sec) }}</td>
          <td>
            <span class="status-badge" :class="s.status === 'active' ? 'status-active' : 'status-ended'">
              {{ s.status === 'active' ? '在線' : '已結束' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-text">尚無登入記錄</div>
  </div>
</template>
