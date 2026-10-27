<template>
  <article class="user-card card-surface">
    <button class="user-main" type="button" @click="$emit('select', user)">
      <div class="user-title">
        <strong>{{ user.name }}</strong>
        <span>{{ genderAgeText }}</span>
      </div>

      <div class="tag-row">
        <span v-for="tag in user.tags" :key="tag" class="user-tag">{{ tag }}</span>
        <span v-if="!user.tags?.length" class="empty-text">暂无明显特征</span>
      </div>

      <div class="scale-status">
        <span>{{ scaleStatusLabel }}</span>
        <strong>{{ scaleStatusText }}</strong>
      </div>
    </button>

    <div class="user-side">
      <span :class="['risk-pill', riskClass]">{{ riskText }}</span>
      <div class="user-actions">
        <button
          v-if="showInterveneButton"
          class="primary-button intervene-button"
          type="button"
          @click="$emit('intervene', user)"
        >
          {{ user.hasActiveIntervention ? '进入人工介入' : '人工介入' }}
        </button>
        <button class="ghost-button refresh-button" type="button" :disabled="refreshing" @click="$emit('refresh-risk', user)">
          {{ refreshing ? '评估中...' : '刷新风险评估' }}
        </button>
      </div>
      <small>{{ user.activeAt }}</small>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  user: { type: Object, required: true },
  refreshing: { type: Boolean, default: false },
});

defineEmits(['select', 'refresh-risk', 'intervene']);

const riskCode = computed(() => {
  if (props.user.riskCode) return props.user.riskCode;
  if (props.user.riskLevel === '高') return 'high';
  if (props.user.riskLevel === '中') return 'medium';
  if (props.user.riskLevel === '低') return 'low';
  return null;
});

const riskText = computed(() => {
  if (!riskCode.value) {
    return props.user.riskLevel || '尚未评估';
  }
  return `${props.user.riskLevel}风险`;
});

const riskClass = computed(() => {
  if (riskCode.value === 'high' || riskCode.value === 'critical') return 'risk-high';
  if (riskCode.value === 'medium') return 'risk-medium';
  if (riskCode.value === 'low') return 'risk-low';
  return 'risk-unassessed';
});

const showInterveneButton = computed(() => props.user.transferRequested || props.user.hasActiveIntervention);

const genderAgeText = computed(() => {
  const parts = [props.user.gender, props.user.age ? `${props.user.age} 岁` : ''].filter(Boolean);
  return parts.join(' · ');
});

const questionnaireRisk = computed(() => props.user.questionnaireRisk || {});

const scaleStatusLabel = computed(() => {
  if (questionnaireRisk.value.hasScore) return '已完成量表';
  if (questionnaireRisk.value.sessionStatus === 'assessment_active') return '量表进行中';
  if (questionnaireRisk.value.sessionStatus === 'assessment_invalid') return '量表已作废';
  return '问卷状态';
});

const scaleStatusText = computed(() => {
  const risk = questionnaireRisk.value;
  const scaleName = risk.activeScaleName || '未绑定量表';
  const answered = Number(risk.answeredItemCount || 0);
  const required = Number(risk.requiredItemCount || 0);

  if (risk.hasScore) {
    return `${scaleName}，完整采集 ${answered}/${required} 题`;
  }
  if (risk.sessionStatus === 'assessment_active') {
    return `${scaleName}，已采集 ${answered}/${required} 题`;
  }
  if (risk.sessionStatus === 'assessment_invalid') {
    return `${scaleName} 未完整，结果不计入风险`;
  }
  return '普通聊天，不进入正式量表计分';
});
</script>

<style scoped>
.user-card {
  width: 100%;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background:
    linear-gradient(135deg, rgba(255,255,255,.9), rgba(247,251,249,.78)),
    radial-gradient(circle at 0% 0%, rgba(141,180,217,.12), transparent 34%);
  border:1px solid rgba(90,117,118,.1);
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}

.user-card:hover {
  transform:translateY(-1px);
  border-color:rgba(43,125,116,.2);
  box-shadow:0 14px 30px rgba(75,111,116,.1);
}

.user-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 16px;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
  border-radius: 16px;
}

.user-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.user-title strong {
  color: var(--text-main);
  font-size: 1.04rem;
}

.user-title span,
.user-side small {
  color: var(--text-soft);
}

.user-title span {
  border-radius:999px;
  padding:3px 8px;
  background:rgba(80,93,96,.07);
  font-size:.78rem;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.user-tag {
  border-radius: 999px;
  padding: 0.36rem 0.72rem;
  background: rgba(227, 238, 247, 0.78);
  color: var(--brand-deep);
  font-size: 0.82rem;
}

.empty-text {
  color: var(--text-soft);
  font-size: 0.82rem;
  line-height: 1.8;
}

.scale-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--text-soft);
  font-size: 0.8rem;
  padding:10px 12px;
  border-radius:14px;
  background:rgba(255,255,255,.58);
  border:1px solid rgba(90,117,118,.08);
}

.scale-status span {
  border-radius: 999px;
  padding: 0.24rem 0.58rem;
  background: rgba(120, 169, 136, 0.16);
  color: #557c63;
  font-weight: 700;
}

.scale-status strong {
  color: var(--brand-deep);
  font-weight: 700;
}

.user-side {
  display: grid;
  justify-items: end;
  gap: 9px;
  min-width: 172px;
}

.user-actions {
  display: grid;
  gap: 8px;
  width: 100%;
}

.risk-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  min-height: 36px;
  padding: 0 0.9rem;
  color: #fff;
  font-size: 0.82rem;
  box-shadow:0 8px 18px rgba(75,111,116,.08);
}

.risk-high {
  background: #d67b6d;
}

.risk-medium {
  background: #d6a55a;
}

.risk-low {
  background: #78a988;
}

.risk-unassessed {
  background: rgba(198, 206, 214, 0.92);
  color: #4e5a63;
}

.refresh-button {
  min-height: 36px;
  padding: 0 0.9rem;
  justify-content: center;
  background:rgba(255,255,255,.76);
}

.intervene-button {
  min-height: 36px;
  padding: 0 0.92rem;
  white-space: nowrap;
  justify-content: center;
}

.refresh-button:disabled {
  cursor: wait;
  opacity: 0.72;
}

@media (max-width: 768px) {
  .user-card {
    align-items: stretch;
    flex-direction: column;
  }

  .user-side {
    width: 100%;
    justify-items: stretch;
  }

  .user-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
