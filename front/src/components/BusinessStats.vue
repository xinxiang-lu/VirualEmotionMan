<template>
  <section class="stats-page">
    <div class="stats-grid">
      <StatsCard v-for="item in businessStats" :key="item.label" :label="item.label" :value="item.value" :tone="item.tone" />
    </div>

    <div class="trend-grid">
      <article v-for="item in businessTrendCards" :key="item.key || item.title" class="trend-card card-surface">
        <div class="trend-header">
          <div>
            <h2>{{ item.title }}</h2>
            <span class="metric-label">{{ item.metricLabel }}</span>
          </div>
          <strong class="metric-value">{{ item.metricValue }}</strong>
        </div>

        <div v-if="item.chartType === 'stacked'" class="chart-panel stacked-panel">
          <div class="legend-row">
            <span
              v-for="legend in item.legend || []"
              :key="legend.label"
              :class="['legend-pill', `legend-${legend.tone}`]"
            >
              {{ legend.label }}
            </span>
          </div>

          <div class="chart-grid stacked-chart">
            <div v-for="point in item.series || []" :key="point.date" class="chart-day">
              <div class="stacked-bar">
                <template v-if="stackTotal(point)">
                  <span class="segment segment-high" :style="stackStyle(point.high)"></span>
                  <span class="segment segment-medium" :style="stackStyle(point.medium)"></span>
                  <span class="segment segment-low" :style="stackStyle(point.low)"></span>
                  <span class="segment segment-unassessed" :style="stackStyle(point.unassessed)"></span>
                </template>
                <span v-else class="segment segment-empty" :style="{ flexGrow: 1 }"></span>
              </div>
              <strong class="day-value">中高 {{ point.mediumHigh }}</strong>
              <span class="day-label">{{ point.label }}</span>
            </div>
          </div>
        </div>

        <div v-else class="chart-panel">
          <div class="chart-grid bar-chart">
            <div v-for="point in item.series || []" :key="point.date" class="chart-day">
              <div class="bar-shell">
                <span class="bar-fill" :style="barStyle(point.value, item.series || [])"></span>
              </div>
              <strong class="day-value">{{ point.value }}</strong>
              <span class="day-label">{{ point.label }}</span>
              <span class="day-meta">{{ pointMeta(item.key, point) }}</span>
            </div>
          </div>
        </div>

        <div class="breakdown-row">
          <div v-for="detail in item.breakdown || []" :key="detail.label" class="breakdown-chip">
            <span>{{ detail.label }}</span>
            <strong>{{ detail.value }}</strong>
          </div>
        </div>

        <p>{{ item.description }}</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { fetchBusinessStats } from '@/api/admin';
import StatsCard from '@/components/StatsCard.vue';

const businessStats = ref([]);
const businessTrendCards = ref([]);

const maxSeriesValue = (series) => {
  const values = (series || []).map((item) => Number(item.value) || 0);
  return Math.max(0, ...values);
};

const barStyle = (value, series) => {
  const maxValue = maxSeriesValue(series);
  if (maxValue <= 0) {
    return { height: '8%' };
  }
  const ratio = (Number(value) || 0) / maxValue;
  return { height: `${Math.max(8, Math.round(ratio * 100))}%` };
};

const stackStyle = (value) => ({ flexGrow: Number(value) || 0 });

const stackTotal = (point) =>
  (Number(point?.high) || 0) +
  (Number(point?.medium) || 0) +
  (Number(point?.low) || 0) +
  (Number(point?.unassessed) || 0);

const pointMeta = (key, point) => {
  if (key === 'dialogues') {
    return `${point.activeUserCount || 0} 人活跃`;
  }
  if (key === 'assessments') {
    if (point.avgStressIndex === null || point.avgStressIndex === undefined) {
      return '压力暂无';
    }
    return `压 ${point.avgStressIndex}`;
  }
  return point.detail || '';
};

onMounted(async () => {
  try {
    const data = await fetchBusinessStats();
    businessStats.value = data.stats || [];
    businessTrendCards.value = data.trend_cards || [];
  } catch (error) {
    window.alert(error?.message || '业务统计加载失败，请稍后再试。');
  }
});
</script>

<style scoped>
.stats-page,
.stats-grid,
.trend-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.trend-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.trend-card {
  padding: 20px;
  display: grid;
  gap: 16px;
}

.trend-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}

.trend-card h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 1.05rem;
}

.metric-label {
  display: inline-block;
  margin-top: 8px;
  color: var(--text-soft);
  font-size: 0.84rem;
}

.metric-value {
  color: var(--text-main);
  font-size: 1.8rem;
  line-height: 1;
}

.chart-panel {
  min-height: 220px;
  border-radius: 22px;
  padding: 16px;
  background: linear-gradient(135deg, rgba(223, 235, 247, 0.72), rgba(233, 240, 235, 0.72));
}

.stacked-panel {
  display: grid;
  gap: 12px;
}

.legend-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-pill {
  border-radius: 999px;
  padding: 0.26rem 0.62rem;
  font-size: 0.74rem;
  color: #fff;
}

.legend-high {
  background: #d67b6d;
}

.legend-medium {
  background: #d6a55a;
}

.legend-low {
  background: #78a988;
}

.legend-unassessed {
  background: #9aa7b2;
}

.chart-grid {
  min-height: 164px;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
  align-items: end;
}

.chart-day {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.bar-shell,
.stacked-bar {
  width: 100%;
  min-height: 140px;
  border-radius: 18px;
  overflow: hidden;
  display: flex;
  align-items: end;
  justify-content: center;
  background: rgba(255, 255, 255, 0.52);
}

.bar-fill {
  width: 100%;
  border-radius: 18px 18px 6px 6px;
  background: linear-gradient(180deg, rgba(102, 145, 178, 0.88), rgba(60, 96, 132, 0.96));
}

.stacked-bar {
  flex-direction: column-reverse;
}

.segment {
  width: 100%;
}

.segment-high {
  background: #d67b6d;
}

.segment-medium {
  background: #d6a55a;
}

.segment-low {
  background: #78a988;
}

.segment-unassessed,
.segment-empty {
  background: rgba(184, 194, 202, 0.92);
}

.day-value {
  color: var(--text-main);
  font-size: 0.88rem;
}

.day-label,
.day-meta {
  color: var(--text-soft);
  font-size: 0.74rem;
  text-align: center;
}

.breakdown-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.breakdown-chip {
  min-width: 110px;
  border-radius: 16px;
  padding: 10px 12px;
  display: grid;
  gap: 6px;
  background: rgba(255, 255, 255, 0.72);
}

.breakdown-chip span {
  color: var(--text-soft);
  font-size: 0.78rem;
}

.breakdown-chip strong {
  color: var(--text-main);
  font-size: 0.96rem;
}

.trend-card p {
  margin: 0;
  color: var(--text-soft);
  line-height: 1.75;
}

@media (max-width: 1180px) {
  .trend-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
