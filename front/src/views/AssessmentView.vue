<template>
  <section class="assessment-view">
    <div class="action-bar card-surface">
      <div class="action-copy">
        <button class="ghost-button back-button" type="button" @click="goBackToChat">返回数字人页面</button>
        <strong>状态评估</strong>
        <p>根据近期对话与多模态信息生成最新状态总结，并同步更新压力指数。</p>
      </div>
      <button class="primary-button" type="button" :disabled="generating" @click="handleGenerateAssessment">
        {{ generating ? '生成中...' : '生成最新评估' }}
      </button>
    </div>

    <AssessmentSummary :summary="summary" :cards="cards" />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchAssessmentDashboard, generateAssessmentDashboard } from '@/api/assessment';
import AssessmentSummary from '@/components/AssessmentSummary.vue';

const router = useRouter();
const summary = ref({
  mood: '',
  stressIndex: '',
  updatedAt: '',
  trend: '',
  advice: '',
});
const cards = ref([]);
const generating = ref(false);

const goBackToChat = () => {
  router.push({ name: 'chat' });
};

const loadAssessmentDashboard = async () => {
  const data = await fetchAssessmentDashboard();
  summary.value = data.summary || summary.value;
  cards.value = data.cards || [];
};

const handleGenerateAssessment = async () => {
  if (generating.value) return;

  generating.value = true;
  try {
    const data = await generateAssessmentDashboard();
    summary.value = data.summary || summary.value;
    cards.value = data.cards || cards.value;
    window.alert(data?.message || '状态评估已生成');
  } catch (error) {
    window.alert(error?.message || '状态评估生成失败，请稍后再试。');
  } finally {
    generating.value = false;
  }
};

onMounted(async () => {
  try {
    await loadAssessmentDashboard();
  } catch (error) {
    window.alert(error?.message || '状态评估数据加载失败，请稍后再试。');
  }
});
</script>

<style scoped>
.assessment-view {
  display: grid;
  gap: 20px;
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px;
}

.action-copy {
  display: grid;
  gap: 10px;
}

.back-button {
  justify-self: start;
}

.action-bar strong {
  color: var(--text-main);
  font-size: 1.02rem;
}

.action-bar p {
  margin: 8px 0 0;
  color: var(--text-soft);
  line-height: 1.7;
}

.action-bar button:disabled {
  cursor: wait;
  opacity: 0.72;
}

@media (max-width: 768px) {
  .action-bar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
