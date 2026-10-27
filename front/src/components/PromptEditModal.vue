<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <section class="modal-panel card-surface">
      <header class="modal-header">
        <div>
          <h2>{{ title }}</h2>
          <p>{{ descriptionText }}</p>
        </div>
        <button class="close-button" type="button" @click="$emit('close')">关闭</button>
      </header>

      <textarea v-model="localPrompt" class="prompt-textarea" rows="8" />

      <div class="modal-actions">
        <button class="ghost-button" type="button" @click="$emit('close')">取消</button>
        <button class="primary-button" type="button" @click="$emit('save', localPrompt)">保存</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';

const props = defineProps({
  visible: { type: Boolean, default: false },
  prompt: { type: String, default: '' },
  userName: { type: String, default: '' },
  title: { type: String, default: '调整 AI 提示词' },
  description: { type: String, default: '' },
});

defineEmits(['close', 'save']);

const localPrompt = ref('');
const descriptionText = computed(() => {
  if (props.description) return props.description;
  if (props.userName) return `正在编辑 ${props.userName} 的个性化提示词，保存后会直接影响后续对话。`;
  return '保存后会直接影响后续对话，请谨慎调整。';
});

watch(
  () => props.prompt,
  (value) => {
    localPrompt.value = value || '';
  },
  { immediate: true },
);
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(48, 61, 67, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.modal-panel {
  width: min(760px, 100%);
  padding: 24px;
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

.prompt-textarea {
  width: 100%;
  margin-top: 20px;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  padding: 1rem;
  color: var(--text-main);
  resize: vertical;
  outline: none;
}

.modal-actions {
  margin-top: 18px;
  justify-content: end;
}
</style>
