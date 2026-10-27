<template>
  <section class="ops-page">
    <div class="stats-grid">
      <StatsCard v-for="item in opsStats" :key="item.label" :label="item.label" :value="item.value" :tone="item.tone" />
    </div>

    <section class="log-panel card-surface">
      <div class="panel-header">
        <h2>最近日志摘要</h2>
        <span>近 24 小时</span>
      </div>

      <div class="log-list">
        <article v-for="log in opsLogs" :key="log.id" class="log-item">
          <div class="log-top">
            <span :class="['log-level', levelClass(log.level)]">{{ log.level }}</span>
            <time>{{ log.time }}</time>
          </div>
          <p>{{ log.message }}</p>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { fetchOpsStats } from '@/api/admin';
import StatsCard from '@/components/StatsCard.vue';
const opsStats = ref([]);
const opsLogs = ref([]);

const levelClass = (level) => {
  if (level === '异常') return 'is-error';
  if (level === '警告') return 'is-warn';
  return 'is-ok';
};

onMounted(async () => {
  try {
    const data = await fetchOpsStats();
    opsStats.value = data.stats || [];
    opsLogs.value = data.logs || [];
  } catch (error) {
    window.alert(error?.message || '运维统计加载失败，请稍后再试。');
  }
});
</script>

<style scoped>
.ops-page,
.stats-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.log-panel {
  padding: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-header h2 {
  margin: 0;
  color: var(--text-main);
}

.panel-header span {
  color: var(--text-soft);
}

.log-list {
  margin-top: 18px;
  display: grid;
  gap: 12px;
}

.log-item {
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
}

.log-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.log-level {
  border-radius: 999px;
  padding: 0.34rem 0.68rem;
  color: #fff;
  font-size: 0.8rem;
}

.is-ok {
  background: #78a988;
}

.is-warn {
  background: #d6a55a;
}

.is-error {
  background: #d67b6d;
}

.log-item time,
.log-item p {
  color: var(--text-soft);
}

.log-item p {
  margin: 12px 0 0;
  line-height: 1.75;
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
