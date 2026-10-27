<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <section class="modal-panel card-surface">
      <header class="modal-header">
        <div>
          <h2>个性化设置</h2>
          <p>以下设置会保存到当前账号，并在后续对话中持续生效。</p>
        </div>
        <button class="close-button" type="button" @click="$emit('close')">关闭</button>
      </header>

      <div class="form-grid">
        <section class="field field--stacked">
          <div class="field-head">
            <span>2D 数字人形象</span>
            <small>如果不改，会继续使用系统默认形象。</small>
          </div>

          <div class="avatar-options">
            <button
              v-for="item in avatarOptions"
              :key="item.code"
              :class="['avatar-option', draft.avatar === item.code ? 'is-active' : '']"
              type="button"
              @click="draft.avatar = item.code"
            >
              <div class="avatar-copy">
                <div class="avatar-copy-top">
                  <strong>{{ item.label }}</strong>
                  <span v-if="item.code === defaultAvatarCode" class="default-pill">系统默认</span>
                </div>
                <span>{{ item.code }}</span>
              </div>
            </button>
          </div>
        </section>

        <label class="field">
          <span>给 LLM 的个性化提示词</span>
          <textarea v-model="draft.systemPrompt" rows="5" />
        </label>

        <section class="field field--stacked">
          <div class="field-head">
            <span>语速</span>
            <small>两端做了增强映射，拖到偏慢或偏快时，语音变化会比之前更明显。</small>
          </div>

          <div class="speed-card">
            <div class="speed-summary">
              <strong>{{ speedLabel }}</strong>
              <span>{{ effectiveSpeedPercent }}</span>
            </div>
            <input
              v-model.number="draft.voiceSpeed"
              class="speed-slider"
              type="range"
              min="0.8"
              max="1.2"
              step="0.05"
            />
            <div class="speed-scale">
              <span>很慢</span>
              <span>正常</span>
              <span>很快</span>
            </div>
          </div>
        </section>
      </div>

      <div class="modal-actions">
        <button class="ghost-button" type="button" @click="$emit('close')">取消</button>
        <button class="primary-button" type="button" @click="save">保存设置</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue';
import { normalizeLive2dModelCode } from '@/config/live2dModels';

const props = defineProps({
  visible: { type: Boolean, default: false },
  settings: { type: Object, default: () => ({}) },
});

const emit = defineEmits(['close', 'save']);
const draft = reactive({ systemPrompt: '', avatar: '', voiceSpeed: 1 });
const UI_MIN_SPEED = 0.8;
const UI_MAX_SPEED = 1.2;
const EFFECTIVE_MIN_SPEED = 0.6;
const EFFECTIVE_MAX_SPEED = 1.4;

const availableModels = computed(() => props.settings?.availableAvatars || []);
const defaultAvatarCode = computed(() => normalizeLive2dModelCode(props.settings?.defaultAvatarCode || 'haru'));
const avatarOptions = computed(() =>
  availableModels.value.map((item) => ({
    ...item,
    code: normalizeLive2dModelCode(item.code),
  })),
);
const resolveEffectiveSpeed = (value) => {
  const numeric = Number(value || 1);
  if (numeric === 1) return 1;
  if (numeric < 1) {
    const ratio = (1 - numeric) / (1 - UI_MIN_SPEED);
    return Number((1 - ratio * (1 - EFFECTIVE_MIN_SPEED)).toFixed(2));
  }
  const ratio = (numeric - 1) / (UI_MAX_SPEED - 1);
  return Number((1 + ratio * (EFFECTIVE_MAX_SPEED - 1)).toFixed(2));
};
const effectiveSpeedPercent = computed(() => `${Math.round(resolveEffectiveSpeed(draft.voiceSpeed) * 100)}%`);
const speedLabel = computed(() => {
  const effective = resolveEffectiveSpeed(draft.voiceSpeed);
  if (effective <= 0.7) return '很慢';
  if (effective <= 0.85) return '偏慢';
  if (effective >= 1.3) return '很快';
  if (effective >= 1.15) return '偏快';
  return '正常';
});

watch(
  () => props.settings,
  (value) => {
    draft.systemPrompt = value?.systemPrompt || '';
    draft.avatar = normalizeLive2dModelCode(
      value?.avatar || value?.availableAvatars?.[0]?.code || value?.defaultAvatarCode || 'haru',
    );
    draft.voiceSpeed = Number(value?.voiceSpeed || 1);
  },
  { immediate: true, deep: true },
);

const save = () => emit('save', { ...draft });
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(48, 61, 67, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.modal-panel {
  width: min(760px, 100%);
  max-height: min(860px, calc(100vh - 48px));
  padding: 24px;
  overflow: auto;
}

.modal-header,
.modal-actions {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}

.modal-header h2 {
  margin: 0;
  color: var(--text-main);
}

.modal-header p {
  margin: 10px 0 0;
  color: var(--text-soft);
}

.close-button {
  border: none;
  background: transparent;
  color: var(--text-soft);
}

.form-grid {
  margin-top: 20px;
  display: grid;
  gap: 18px;
}

.field {
  display: grid;
  gap: 8px;
}

.field--stacked {
  gap: 12px;
}

.field-head {
  display: grid;
  gap: 4px;
}

.field span {
  color: var(--text-main);
  font-weight: 600;
}

.field small {
  color: var(--text-soft);
}

.field textarea {
  width: 100%;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.8);
  padding: 0.9rem 1rem;
  color: var(--text-main);
  outline: none;
}

.speed-card {
  border: 1px solid rgba(122, 158, 178, 0.16);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  padding: 14px 16px;
  display: grid;
  gap: 12px;
}

.speed-summary,
.speed-scale {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.speed-summary strong {
  color: var(--text-main);
  font-size: 0.98rem;
}

.speed-summary span,
.speed-scale span {
  color: var(--text-soft);
  font-size: 0.82rem;
}

.speed-slider {
  width: 100%;
  accent-color: #6f8ba1;
}

.avatar-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.avatar-option {
  border: 1px solid rgba(122, 158, 178, 0.18);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.78);
  padding: 16px 18px;
  display: block;
  text-align: left;
  transition: border-color 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
}

.avatar-option:hover {
  border-color: rgba(122, 158, 178, 0.3);
  transform: translateY(-1px);
}

.avatar-option.is-active {
  border-color: rgba(122, 158, 178, 0.42);
  background: rgba(224, 237, 248, 0.88);
  box-shadow: 0 12px 24px rgba(122, 158, 178, 0.14);
}

.avatar-copy {
  min-width: 0;
  display: grid;
  gap: 10px;
  align-content: start;
}

.avatar-copy-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.avatar-copy strong {
  color: var(--text-main);
  font-size: 1rem;
}

.avatar-copy span {
  color: var(--text-soft);
  font-size: 0.8rem;
}

.default-pill {
  padding: 0.16rem 0.52rem;
  border-radius: 999px;
  background: rgba(90, 126, 147, 0.12);
  color: var(--brand-deep);
  font-size: 0.74rem;
  font-weight: 700;
}

.modal-actions {
  margin-top: 20px;
  justify-content: end;
}

@media (max-width: 720px) {
  .avatar-options {
    grid-template-columns: 1fr;
  }

  .avatar-option {
    padding: 14px 16px;
  }
}
</style>
