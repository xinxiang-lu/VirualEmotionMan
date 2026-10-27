<template>
  <transition name="drawer-fade">
    <div v-if="visible" class="drawer-mask" @click.self="$emit('close')">
      <aside class="drawer-panel card-surface">
        <header class="drawer-header">
          <div>
            <h2>{{ user?.name || '用户详情' }}</h2>
            <p>{{ user?.account || '' }}</p>
          </div>
          <button class="close-button" type="button" @click="$emit('close')">关闭</button>
        </header>

        <div v-if="user" class="drawer-body">
          <section class="panel-block compact-block">
            <div class="detail-row">
              <span class="detail-label">风险</span>
              <div class="status-row">
                <span :class="['risk-pill', riskClass]">{{ riskText }}</span>
                <small>{{ user.activeAt }}</small>
              </div>
            </div>
            <div class="detail-row detail-row--feature">
              <span class="detail-label">特征</span>
              <div class="tag-row">
                <span v-for="tag in user.tags" :key="tag" class="soft-tag">{{ tag }}</span>
                <span v-if="!user.tags?.length" class="empty-text">暂无明显特征</span>
              </div>
            </div>
          </section>

          <section class="panel-block">
            <div class="panel-title-row">
              <h3>AI画像与量表依据</h3>
              <span class="source-badge">{{ activeScaleText }}</span>
            </div>

            <div class="insight-grid">
              <div class="insight-card">
                <div class="insight-card-title">
                  <strong>动态用户画像</strong>
                  <div class="title-actions">
                    <small v-if="profileMemoryUpdatedAt">更新于 {{ profileMemoryUpdatedAt }}</small>
                    <button
                      class="mini-button"
                      type="button"
                      :disabled="profileMemoryLoading"
                      @click="$emit('refresh-profile-memory', user)"
                    >
                      {{ profileMemoryLoading ? '刷新中...' : '基于历史对话刷新' }}
                    </button>
                  </div>
                </div>
                <div v-if="profileMemoryItems.length" class="memory-list">
                  <div v-for="item in profileMemoryItems" :key="item.key" :class="['memory-item', item.empty ? 'is-empty' : '']">
                    <span>{{ item.label }}</span>
                    <p v-if="Array.isArray(item.value)">{{ item.value.join('、') }}</p>
                    <p v-else>{{ item.value }}</p>
                  </div>
                </div>
                <p v-else class="state-text">{{ user.profileMemory?.emptyText || '暂无动态画像记录。' }}</p>
              </div>

              <div class="insight-card">
                <div class="insight-card-title">
                  <strong>{{ questionnaireRisk?.questionnaireName || '单量表对话式心理状态评估' }}</strong>
                  <small v-if="questionnaireUpdatedAt">更新于 {{ questionnaireUpdatedAt }}</small>
                </div>
                <p class="questionnaire-desc">
                  {{ questionnaireRisk?.questionnaireDescription || '每次评估只绑定一张心理量表，完整后才进入正式评分。' }}
                </p>

                <div v-if="currentSession?.status === 'assessment_active'" class="active-session-card">
                  <div>
                    <span>当前进行中的问卷</span>
                    <strong>{{ currentSession.scaleName || '未命名量表' }}</strong>
                  </div>
                  <div class="active-session-progress">
                    <b>{{ currentSession.answeredItemCount || 0 }}/{{ currentSession.requiredItemCount || 0 }}</b>
                    <small>已完成题项</small>
                  </div>
                  <p v-if="currentSession.nextQuestion">
                    下一题：{{ currentSession.nextQuestion }}
                  </p>
                </div>

                <div v-if="availableQuestionnaireScales.length" class="scale-launcher">
                  <div class="scale-recommend">
                    <span>自动推荐</span>
                    <strong>{{ recommendedScale?.name || recommendedScale?.id || '暂无' }}</strong>
                    <p>{{ questionnaireRisk?.recommendedScale?.reason || '系统会根据画像线索推荐优先量表。' }}</p>
                  </div>
                  <div class="scale-control-panel">
                    <label>
                      <span>人工选择量表</span>
                      <select v-model="selectedScaleId" class="scale-select">
                        <option v-for="scale in availableQuestionnaireScales" :key="scale.id || scale.name" :value="scale.id || scale.name">
                          {{ scale.name || scale.label }} · {{ scale.itemCount || scale.items?.length || 0 }} 题
                        </option>
                      </select>
                    </label>
                    <div class="scale-meta">
                      <span>{{ selectedScale?.label || selectedScale?.description || '选择后可发起对话式评估。' }}</span>
                      <small>{{ selectedScale?.timeWindow || '最近两周' }} · {{ selectedScale?.scoreRange || '自动计分' }}</small>
                    </div>
                    <div class="scale-action-row">
                      <button class="scale-button" type="button" @click="$emit('start-questionnaire', user, selectedScale)">
                        发起评估
                      </button>
                      <button class="scale-button scale-button--ghost" type="button" @click="toggleScaleDetail(selectedScale)">
                        {{ openedScaleId === scaleKey(selectedScale) ? '收起题项' : '查看题项' }}
                      </button>
                    </div>
                  </div>
                </div>

                <div v-if="openedScale" class="scale-detail">
                  <div class="scale-detail-title">
                    <strong>{{ openedScale.name }}</strong>
                    <span>{{ openedScale.itemCount || openedScale.items?.length || 0 }} 题 · {{ openedScale.timeWindow || '近两周' }}</span>
                  </div>
                  <p>{{ openedScale.purpose || openedScale.label }}</p>
                  <ol>
                    <li v-for="item in openedScale.items || []" :key="item.code">
                      <span>{{ item.dimensionLabel || item.dimension }} · {{ item.construct }}</span>
                      <p>{{ item.prompt }}</p>
                      <div class="option-row">
                        <b v-for="option in item.options || []" :key="`${item.code}-${option.score}`">
                          {{ option.score }}={{ option.label }}
                        </b>
                      </div>
                    </li>
                  </ol>
                </div>

                <div class="score-summary">
                  <span :class="['risk-pill', currentSessionClass]">{{ sessionStatusText }}</span>
                  <span v-if="currentSession?.scaleName">当前 {{ currentSession.scaleName }}</span>
                  <span>
                    完成 {{ currentSession?.answeredItemCount || questionnaireRisk?.answeredItemCount || 0 }}/{{
                      currentSession?.requiredItemCount || questionnaireRisk?.requiredItemCount || 0
                    }}
                  </span>
                </div>

                <div v-if="questionnaireRisk?.hasScore" class="score-summary score-summary--sub">
                  <span :class="['risk-pill', questionnaireRiskClass]">{{ latestScore?.riskLevel || questionnaireRisk.riskLevel }}风险</span>
                  <span>最新正式结果 {{ latestScore?.scaleName || questionnaireRisk.activeScaleName }}</span>
                  <span>总分 {{ latestScore?.totalScore ?? questionnaireRisk.totalScore }}</span>
                  <span>压力 {{ latestScore?.stressIndex ?? questionnaireRisk.stressIndex }}/100</span>
                </div>

                <p class="state-text">{{ questionnaireRisk?.basisText || '暂未形成可用量表评分。' }}</p>

                <div v-if="questionnaireDimensionScores.length" class="dimension-row">
                  <span v-for="item in questionnaireDimensionScores" :key="item.dimension" class="score-chip">
                    {{ item.label }} {{ item.score }}
                  </span>
                </div>

                <div v-if="questionnaireAnswers.length" class="answer-list">
                  <div v-for="answer in questionnaireAnswers" :key="`${answer.itemCode}-${answer.createdAt}`" class="answer-item">
                    <div class="answer-title-row">
                      <span>{{ answerTitle(answer) }}</span>
                      <small>{{ answerSourceText(answer) }}</small>
                    </div>
                    <p>{{ answer.evidence }}</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="panel-block">
            <div class="panel-title-row">
              <h3>心理档案分析结果</h3>
              <button class="ghost-button" type="button" :disabled="reportLoading" @click="$emit('refresh-report', user)">
                {{ reportLoading ? '生成中...' : '刷新档案报告' }}
              </button>
            </div>

            <p v-if="reportGeneratedAt" class="meta-text">最近生成：{{ reportGeneratedAt }}</p>
            <p v-if="reportLoading" class="state-text">正在整理用户画像、历史状态和近期对话，请稍候。</p>
            <p v-else-if="reportError" class="error-text">{{ reportError }}</p>
            <MarkdownReport v-else-if="reportMarkdown" :content="reportMarkdown" />
            <p v-else class="state-text">{{ user.summary }}</p>
          </section>

          <section class="panel-block action-panel">
            <div class="panel-title-row">
              <h3>操作</h3>
              <span class="source-badge">当前用户</span>
            </div>
            <div class="action-grid">
              <button class="action-card" type="button" @click="$emit('edit-prompt', user)">
                <strong>调整 AI 提示词</strong>
                <span>修改该用户的个性化陪伴风格和回复偏好。</span>
              </button>
              <button
                :class="['action-card', 'action-card--primary', isDangerRisk(user) ? 'action-card--danger' : '']"
                type="button"
                @click="$emit('intervene', user)"
              >
                <strong>人工介入</strong>
                <span>进入人工接管页面，查看消息并发送管理员回复。</span>
              </button>
            </div>
          </section>
        </div>
      </aside>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import MarkdownReport from '@/components/MarkdownReport.vue';

const props = defineProps({
  visible: { type: Boolean, default: false },
  user: { type: Object, default: null },
  reportMarkdown: { type: String, default: '' },
  reportLoading: { type: Boolean, default: false },
  reportError: { type: String, default: '' },
  reportGeneratedAt: { type: String, default: '' },
  questionnaireScales: { type: Array, default: () => [] },
  profileMemoryLoading: { type: Boolean, default: false },
});

defineEmits(['close', 'edit-prompt', 'intervene', 'refresh-report', 'start-questionnaire', 'refresh-profile-memory']);

const riskCode = computed(() => {
  if (props.user?.riskCode) return props.user.riskCode;
  if (props.user?.riskLevel === '高') return 'high';
  if (props.user?.riskLevel === '中') return 'medium';
  if (props.user?.riskLevel === '低') return 'low';
  return null;
});

const riskText = computed(() => {
  if (!riskCode.value) return props.user?.riskLevel || '尚未评估';
  return `${props.user?.riskLevel || ''}风险`;
});

const riskClass = computed(() => {
  if (riskCode.value === 'high' || riskCode.value === 'critical') return 'risk-high';
  if (riskCode.value === 'medium') return 'risk-medium';
  if (riskCode.value === 'low') return 'risk-low';
  return 'risk-unassessed';
});

const profileMemoryItems = computed(() => props.user?.profileMemory?.items || []);
const profileMemoryUpdatedAt = computed(() => props.user?.profileMemory?.updatedAt || '');
const questionnaireRisk = computed(() => props.user?.questionnaireRisk || null);
const currentSession = computed(() => questionnaireRisk.value?.currentSession || null);
const latestScore = computed(() => questionnaireRisk.value?.latestScore || null);
const questionnaireUpdatedAt = computed(() => questionnaireRisk.value?.updatedAt || '');
const questionnaireDimensionScores = computed(() => questionnaireRisk.value?.dimensionScores || []);
const questionnaireAnswers = computed(() => {
  const risk = questionnaireRisk.value;
  if (!risk?.hasScore && risk?.sessionStatus !== 'assessment_active') return [];
  return risk?.answers || [];
});
const availableQuestionnaireScales = computed(() => {
  if (props.questionnaireScales.length) return props.questionnaireScales;
  return questionnaireRisk.value?.referenceScales || [];
});
const openedScaleId = ref('');
const selectedScaleId = ref('');
const scaleKey = (scale) => scale?.id || scale?.name || '';
const openedScale = computed(() => availableQuestionnaireScales.value.find((scale) => scaleKey(scale) === openedScaleId.value) || null);
const recommendedScale = computed(() => {
  const target = questionnaireRisk.value?.recommendedScale?.scaleId;
  return availableQuestionnaireScales.value.find((scale) => scaleKey(scale) === target) || availableQuestionnaireScales.value[0] || null;
});
const selectedScale = computed(
  () =>
    availableQuestionnaireScales.value.find((scale) => scaleKey(scale) === selectedScaleId.value) ||
    recommendedScale.value ||
    availableQuestionnaireScales.value[0] ||
    null,
);

const activeScaleText = computed(() => {
  const scaleName = questionnaireRisk.value?.activeScaleName;
  if (scaleName) return `当前量表：${scaleName}`;
  return '普通聊天不计入正式量表';
});

const sessionStatusText = computed(() => {
  const status = questionnaireRisk.value?.sessionStatus;
  if (status === 'assessment_active') return '评估进行中';
  if (status === 'assessment_invalid') return '未完成作废';
  if (status === 'assessment_completed') return '已完成';
  return '尚未评估';
});

const answerTitle = (answer) => {
  const scale = answer.referenceScale || answer.dimensionLabel || '';
  const construct = answer.construct ? ` · ${answer.construct}` : '';
  return `${scale}${construct}：${answer.score}${answer.maxScore ? `/${answer.maxScore}` : ''}`;
};

const answerSourceText = (answer) => {
  const source = answer.source === 'scale_session_ai' ? 'AI评分' : '规则评分';
  const confidence = Number(answer.confidence || 0);
  return `${source} · 置信度 ${Math.round(confidence * 100)}%`;
};

const toggleScaleDetail = (scale) => {
  const key = scaleKey(scale);
  if (!key) return;
  openedScaleId.value = openedScaleId.value === key ? '' : key;
};

watch(
  [recommendedScale, availableQuestionnaireScales],
  () => {
    if (!selectedScaleId.value && recommendedScale.value) {
      selectedScaleId.value = scaleKey(recommendedScale.value);
    }
  },
  { immediate: true },
);

const questionnaireRiskClass = computed(() => {
  const code = latestScore.value?.riskCode || questionnaireRisk.value?.riskCode;
  if (code === 'high' || code === 'critical') return 'risk-high';
  if (code === 'medium') return 'risk-medium';
  if (code === 'low') return 'risk-low';
  return 'risk-unassessed';
});

const currentSessionClass = computed(() => {
  const status = currentSession.value?.status || questionnaireRisk.value?.sessionStatus;
  if (status === 'assessment_active') return 'risk-medium';
  if (status === 'assessment_completed') return 'risk-low';
  if (status === 'assessment_invalid') return 'risk-unassessed';
  return 'risk-unassessed';
});

const isDangerRisk = (user) => {
  if (!user) return false;
  if (user.riskCode) return ['medium', 'high', 'critical'].includes(user.riskCode);
  return user.riskLevel === '中' || user.riskLevel === '高';
};
</script>

<style scoped>
.drawer-mask { position:fixed; inset:0; z-index:45; background:rgba(48,61,67,.28); backdrop-filter:blur(4px); }
.drawer-panel {
  position:absolute;
  top:0;
  right:0;
  width:min(720px, 100%);
  height:100%;
  padding:26px;
  border-radius:24px 0 0 24px;
  overflow:auto;
  background:
    radial-gradient(circle at 10% 0%, rgba(141,180,217,.16), transparent 32%),
    rgba(255,255,255,.9);
}
.drawer-header {
  display:flex;
  align-items:start;
  justify-content:space-between;
  gap:12px;
  padding-bottom:18px;
  border-bottom:1px solid rgba(90,117,118,.12);
}
.drawer-header h2 { margin:0; color:var(--text-main); }
.drawer-header p { margin:10px 0 0; color:var(--text-soft); }
.close-button { border:1px solid rgba(90,117,118,.12); border-radius:999px; background:rgba(255,255,255,.74); color:var(--text-soft); cursor:pointer; font-weight:700; padding:7px 12px; }
.drawer-body { margin-top:20px; display:grid; gap:18px; }
.panel-block { border:1px solid rgba(90,117,118,.14); border-radius:18px; padding:18px; background:rgba(255,255,255,.76); box-shadow:0 10px 26px rgba(75,111,116,.07); }
.compact-block { display:grid; gap:14px; }
.detail-row { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.detail-row--feature { align-items:start; }
.detail-label { color:var(--text-soft); font-size:.92rem; }
.status-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:end; }
.status-row small { color:var(--text-soft); }
.tag-row { display:flex; flex-wrap:wrap; gap:8px; justify-content:end; }
.soft-tag, .score-chip, .reference-chip { border-radius:999px; padding:5px 10px; background:rgba(78,138,126,.1); color:var(--brand-deep); font-size:.82rem; }
.empty-text, .state-text, .meta-text { color:var(--text-soft); line-height:1.7; }
.panel-title-row { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
.panel-title-row h3 { margin:0; color:var(--text-main); }
.source-badge { border-radius:999px; padding:5px 10px; background:rgba(43,125,116,.1); color:var(--brand-deep); font-size:.82rem; white-space:nowrap; }
.insight-grid { display:grid; gap:14px; }
.insight-card { border:1px solid rgba(90,117,118,.12); border-radius:16px; padding:16px; background:rgba(255,255,255,.72); }
.insight-card-title { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
.insight-card-title strong { color:var(--text-main); }
.insight-card-title small { color:var(--text-soft); }
.title-actions { display:flex; align-items:center; justify-content:flex-end; gap:8px; flex-wrap:wrap; }
.mini-button { border:1px solid rgba(43,125,116,.18); border-radius:999px; background:rgba(43,125,116,.08); color:var(--brand-deep); cursor:pointer; font-weight:800; padding:5px 10px; font-size:.78rem; }
.mini-button:disabled { opacity:.62; cursor:not-allowed; }
.memory-list { display:grid; gap:10px; }
.memory-item span, .answer-item span { color:var(--brand-deep); font-weight:700; font-size:.9rem; }
.memory-item.is-empty span, .memory-item.is-empty p { color:var(--text-soft); opacity:.78; }
.answer-title-row { display:flex; justify-content:space-between; gap:8px; align-items:center; flex-wrap:wrap; }
.answer-title-row small { color:var(--text-soft); font-size:.76rem; }
.memory-item p, .answer-item p, .questionnaire-desc { margin:5px 0 0; color:var(--text-soft); line-height:1.7; }
.active-session-card {
  margin:12px 0;
  border:1px solid rgba(226,154,58,.28);
  border-radius:16px;
  padding:14px;
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:8px 12px;
  background:linear-gradient(145deg, rgba(226,154,58,.16), rgba(255,255,255,.78));
}
.active-session-card span { color:#9a6419; font-size:.78rem; font-weight:800; letter-spacing:.04em; }
.active-session-card strong { display:block; margin-top:4px; color:var(--text-main); font-size:1.02rem; }
.active-session-card p { grid-column:1 / -1; margin:2px 0 0; color:var(--text-soft); line-height:1.65; }
.active-session-progress { display:grid; justify-items:end; align-content:center; gap:2px; color:#9a6419; }
.active-session-progress b { font-size:1.08rem; }
.active-session-progress small { color:var(--text-soft); }
.score-summary { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:12px 0; }
.score-summary--sub { margin-top:-4px; }
.score-summary span:not(.risk-pill) { border-radius:999px; padding:5px 10px; background:rgba(80,93,96,.08); color:var(--text-main); font-size:.85rem; }
.scale-launcher { margin:12px 0; display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1.35fr); gap:10px; color:var(--text-soft); font-size:.86rem; }
.scale-recommend { display:grid; gap:5px; border-radius:16px; padding:14px; background:linear-gradient(145deg, rgba(43,125,116,.12), rgba(141,180,217,.1)); }
.scale-recommend strong { color:var(--brand-deep); font-size:1rem; }
.scale-recommend span { color:var(--text-soft); font-size:.78rem; font-weight:800; letter-spacing:.04em; }
.scale-recommend p { margin:0; color:var(--text-soft); line-height:1.65; }
.scale-control-panel { display:grid; gap:9px; border:1px solid rgba(90,117,118,.12); border-radius:16px; padding:14px; background:rgba(255,255,255,.72); }
.scale-control-panel label { display:grid; gap:6px; color:var(--text-soft); font-size:.82rem; }
.scale-select { width:100%; border:1px solid rgba(90,117,118,.18); border-radius:12px; padding:9px 11px; color:var(--text-main); background:#fff; outline:none; }
.scale-meta { display:grid; gap:3px; color:var(--text-main); line-height:1.55; }
.scale-meta small { color:var(--text-soft); }
.scale-action-row { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.scale-button { border:1px solid rgba(43,125,116,.18); border-radius:12px; padding:9px 10px; background:rgba(43,125,116,.1); color:var(--brand-deep); cursor:pointer; font-weight:800; }
.scale-button:hover { border-color:rgba(43,125,116,.38); background:rgba(43,125,116,.14); }
.scale-button--ghost { background:rgba(255,255,255,.82); color:var(--text-soft); }
.scale-detail { margin:12px 0; border:1px dashed rgba(43,125,116,.24); border-radius:16px; padding:14px; background:rgba(255,255,255,.66); }
.scale-detail-title { display:flex; align-items:center; justify-content:space-between; gap:10px; color:var(--text-main); }
.scale-detail-title span, .scale-detail > p { color:var(--text-soft); }
.scale-detail ol { margin:10px 0 0; padding-left:20px; display:grid; gap:8px; }
.scale-detail li span { color:var(--brand-deep); font-weight:700; font-size:.86rem; }
.scale-detail li p { margin:4px 0 0; color:var(--text-main); line-height:1.6; }
.option-row { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
.option-row b { border-radius:999px; padding:3px 8px; background:rgba(80,93,96,.08); color:var(--text-soft); font-size:.78rem; font-weight:700; }
.dimension-row, .answer-list { display:grid; gap:8px; margin-top:12px; }
.answer-item { border-top:1px solid rgba(90,117,118,.12); padding-top:10px; }
.action-panel .panel-title-row { margin-bottom:12px; }
.action-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.action-card { border:1px solid rgba(90,117,118,.14); border-radius:16px; background:rgba(255,255,255,.72); padding:15px; display:grid; gap:7px; text-align:left; cursor:pointer; transition:.18s ease; }
.action-card:hover { transform:translateY(-1px); border-color:rgba(43,125,116,.32); box-shadow:0 12px 28px rgba(75,111,116,.12); }
.action-card strong { color:var(--text-main); font-size:.98rem; }
.action-card span { color:var(--text-soft); line-height:1.6; font-size:.84rem; }
.action-card--primary { background:linear-gradient(145deg, rgba(43,125,116,.13), rgba(141,180,217,.13)); }
.action-card--danger { background:linear-gradient(145deg, rgba(201,80,65,.15), rgba(255,255,255,.72)); border-color:rgba(201,80,65,.24); }
.risk-pill { border-radius:999px; padding:5px 11px; font-size:.86rem; font-weight:800; }
.risk-high { background:rgba(214,78,59,.14); color:#b43a2c; }
.risk-medium { background:rgba(226,154,58,.18); color:#9a6419; }
.risk-low { background:rgba(55,145,112,.16); color:#287455; }
.risk-unassessed { background:rgba(80,93,96,.1); color:var(--text-soft); }
.danger-button { background:#c95041; }
.error-text { color:#b43a2c; }
.drawer-fade-enter-active, .drawer-fade-leave-active { transition:opacity .2s ease; }
.drawer-fade-enter-from, .drawer-fade-leave-to { opacity:0; }
@media (max-width: 720px) {
  .scale-launcher, .scale-action-row, .action-grid { grid-template-columns:1fr; }
}
</style>
