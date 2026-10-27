<template>
  <section class="chat-input card-surface">
    <div class="capture-toolbar">
      <button
        :class="['capture-toggle', videoCaptureActive ? 'is-active' : '']"
        type="button"
        :disabled="sending"
        @click="$emit('toggle-video')"
      >
        {{ videoCaptureActive ? '视频接入已开启' : '开启视频接入' }}
      </button>

      <button
        :class="['capture-toggle', voiceActive ? 'is-active' : '']"
        type="button"
        :disabled="sending"
        @click="$emit('toggle-voice')"
      >
        {{ voiceActive ? '语音接入已开启' : '开启语音接入' }}
      </button>

      <span class="capture-hint">
        点击视频接入时会同步开启语音采集，发送后会自动一起收束本轮音视频片段。
      </span>
    </div>

    <div v-if="videoCaptureStatus" class="capture-status">
      <p>{{ videoCaptureStatus }}</p>
    </div>

    <div v-if="audioFileName || videoFileName" class="media-chip-group">
      <button v-if="audioFileName" class="media-chip" type="button" :disabled="sending" @click="$emit('clear-audio')">
        语音片段: {{ audioFileName }} ×
      </button>
      <button v-if="videoFileName" class="media-chip" type="button" :disabled="sending" @click="$emit('clear-video')">
        视频片段: {{ videoFileName }} ×
      </button>
    </div>

    <textarea
      v-model="localValue"
      class="input-area"
      rows="4"
      placeholder="把你现在想说的话写下来，或者直接开启语音和视频输入。"
      :disabled="sending"
      @keydown="handleKeydown"
    />

    <p v-if="statusText" class="status-text">{{ statusText }}</p>

    <div class="input-actions">
      <span class="send-hint">发送前会自动收束本轮音视频采集结果。</span>
      <button class="send-button" type="button" :disabled="sending" @click="submit">
        {{ sending ? '...' : '发送' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  modelValue: { type: String, default: '' },
  voiceActive: { type: Boolean, default: false },
  videoCaptureActive: { type: Boolean, default: false },
  sending: { type: Boolean, default: false },
  statusText: { type: String, default: '' },
  videoCaptureStatus: { type: String, default: '' },
  audioFileName: { type: String, default: '' },
  videoFileName: { type: String, default: '' },
});

const emit = defineEmits([
  'update:modelValue',
  'send',
  'toggle-voice',
  'toggle-video',
  'clear-audio',
  'clear-video',
]);

const localValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const submit = () => emit('send');

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
};
</script>

<style scoped>
.chat-input { padding:16px; display:grid; gap:14px; }
.capture-toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.capture-toggle { border:none; border-radius:999px; padding:.65rem 1rem; background:rgba(229,239,247,.82); color:var(--text-soft); }
.capture-toggle.is-active { color:#fff; background:linear-gradient(135deg, var(--brand-deep), #7ab39f); }
.capture-hint { color:var(--text-soft); font-size:.82rem; }
.capture-status { display:grid; gap:6px; }
.capture-status p { margin:0; color:var(--brand-deep); font-size:.9rem; }
.media-chip-group { display:flex; flex-wrap:wrap; gap:8px; }
.media-chip { border:none; border-radius:999px; padding:.45rem .75rem; background:rgba(220,236,248,.95); color:var(--text-main); }
.input-area { width:100%; border:none; resize:none; background:transparent; color:var(--text-main); outline:none; line-height:1.75; }
.input-area:disabled { opacity:.72; cursor:wait; }
.status-text { margin:0; color:var(--brand-deep); font-size:.92rem; }
.input-actions { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.send-hint { color:var(--text-soft); font-size:.82rem; }
.send-button { min-width:84px; height:44px; border:none; border-radius:999px; background:linear-gradient(135deg, #7fa8d2 0%, #7bb4a2 100%); color:#fff; font-size:.95rem; padding:0 1rem; }
.capture-toggle:disabled, .send-button:disabled, .media-chip:disabled { opacity:.72; cursor:wait; }
</style>
