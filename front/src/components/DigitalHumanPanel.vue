<template>
  <section class="digital-panel card-surface">
    <header class="panel-head">
      <div class="panel-title-block">
        <span class="panel-tag">2D Digital Human</span>
        <h1>{{ selectedModelLabel }}</h1>
      </div>
      <span class="status-chip">{{ statusLabel }}</span>
    </header>

    <HaruLive2DCanvas
      v-if="selectedModelCode"
      :key="selectedModelCode"
      class="live2d-stage"
      :payload="effectiveLive2dPayload"
      :loading="haruLoading"
      :model-code="selectedModelCode"
      :model-label="selectedModelLabel"
      :reply-sync="replySync"
      :state-mode="stateMode"
    />
    <div v-else class="live2d-stage stage-placeholder">
      <span>正在准备 2D 数字人模型...</span>
    </div>

    <footer class="panel-foot">
      <div class="meta-row">
        <span class="meta-chip">{{ selectedModelLabel }}</span>
        <span v-if="displayPayloadMeta.frameCount" class="meta-chip">{{ displayPayloadMeta.frameCount }} 帧</span>
        <span v-if="displayPayloadMeta.parameterCount" class="meta-chip">{{ displayPayloadMeta.parameterCount }} 参数</span>
        <span v-if="displayPayloadMeta.version" class="meta-chip">{{ displayPayloadMeta.version }}</span>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue';
import HaruLive2DCanvas from '@/components/HaruLive2DCanvas.vue';
import { getLive2dModelConfig, normalizeLive2dModelCode } from '@/config/live2dModels';
import { resolveMediaUrl } from '@/utils/mediaUrl';
import {
  buildAssistantReplyPayload,
  estimateReplyDuration,
  inferAssistantReplyProfile,
} from '@/utils/assistantReplyMotion';

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const parseBackendTimestamp = (value) => {
  if (!value) return NaN;
  const raw = String(value)
    .trim()
    .replace(/(\.\d{3})\d+/, '$1');
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`;
  return new Date(normalized).getTime();
};

const props = defineProps({
  analysis: { type: Object, default: null },
  haruPayload: { type: Object, default: null },
  haruLoading: { type: Boolean, default: false },
  settings: { type: Object, default: () => ({}) },
  messages: { type: Array, default: () => [] },
  sending: { type: Boolean, default: false },
});

const analysisMode = computed(() => props.analysis?.analysis_mode || '');
const settingsReady = computed(() => Array.isArray(props.settings?.availableAvatars) && props.settings.availableAvatars.length > 0);
const selectedModelCode = computed(() => {
  if (!settingsReady.value) return '';
  const fromSettings = props.settings?.selectedAvatar?.code || props.settings?.avatar || '';
  return normalizeLive2dModelCode(fromSettings);
});
const selectedModelLabel = computed(
  () =>
    props.settings?.selectedAvatar?.label ||
    (selectedModelCode.value ? getLive2dModelConfig(selectedModelCode.value).label : '2D Digital Human'),
);
const live2dPayload = computed(
  () =>
    props.haruPayload ||
    props.analysis?.live2d_adapter_payload ||
    props.analysis?.prediction_result?.live2d_adapter_payload ||
    props.analysis?.prediction_result?.haru_adapter_payload ||
    null,
);

const assistantReplyPayload = shallowRef(null);
const activeReplyMessage = shallowRef(null);
const latestAutoPlayedReplyId = ref('');
const allowNextAssistantAutoplay = ref(false);
const assistantHistoryHydrated = ref(false);

const replySync = reactive({
  active: false,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  mouthLevel: 0,
  messageId: '',
  profile: null,
});

let replyAudio = null;
let replyAudioContext = null;
let replyAnalyser = null;
let replySourceNode = null;
let replySourceElement = null;
let replyAnalyserBuffer = null;
let replyMonitorFrameId = 0;

const effectiveLive2dPayload = computed(() => assistantReplyPayload.value || live2dPayload.value);
const latestAssistantMessage = computed(
  () => [...(props.messages || [])].reverse().find((message) => message.sender === 'assistant') || null,
);
const latestUserMessage = computed(
  () => [...(props.messages || [])].reverse().find((message) => message.sender === 'user') || null,
);

const displayPayloadMeta = computed(() => ({
  frameCount: effectiveLive2dPayload.value?.frame_count || effectiveLive2dPayload.value?.parameter_frames?.length || 0,
  parameterCount: effectiveLive2dPayload.value?.parameter_count || effectiveLive2dPayload.value?.parameter_ids?.length || 0,
  version: effectiveLive2dPayload.value?.mapping_version || '',
}));

const isPlayableAudioUrl = (audioUrl) => Boolean(audioUrl && !String(audioUrl).startsWith('__pending__'));

const isRecentlyAnswered = computed(() => {
  const assistantCreatedAt = latestAssistantMessage.value?.createdAt;
  if (!assistantCreatedAt || !effectiveLive2dPayload.value?.parameter_frames?.length) {
    return false;
  }

  const normalizedAssistantTime = parseBackendTimestamp(assistantCreatedAt);
  if (Number.isNaN(normalizedAssistantTime)) {
    return false;
  }

  const userCreatedAt = latestUserMessage.value?.createdAt;
  const userTime = userCreatedAt ? parseBackendTimestamp(userCreatedAt) : NaN;
  if (!Number.isNaN(userTime) && normalizedAssistantTime < userTime) {
    return false;
  }

  return Date.now() - normalizedAssistantTime <= 45000;
});

const stopReplyMonitor = () => {
  if (replyMonitorFrameId) {
    window.cancelAnimationFrame(replyMonitorFrameId);
    replyMonitorFrameId = 0;
  }
};

const isAssistantAudioElement = (element) =>
  typeof window !== 'undefined' &&
  element instanceof window.HTMLAudioElement &&
  element.classList.contains('assistant-audio-player');

const resetReplySync = ({ clearPayload = false } = {}) => {
  stopReplyMonitor();
  replySync.active = false;
  replySync.isPlaying = false;
  replySync.currentTime = 0;
  replySync.duration = 0;
  replySync.mouthLevel = 0;
  replySync.messageId = '';
  replySync.profile = null;
  activeReplyMessage.value = null;
  if (clearPayload) {
    assistantReplyPayload.value = null;
  }
};

const findAssistantReplyMessage = (messageId) =>
  (props.messages || []).find((message) => String(message.id) === String(messageId) && message.sender === 'assistant') || null;

const getAssistantAudioElement = (messageId = '') => {
  if (typeof document === 'undefined') return null;
  const selector = messageId
    ? `.assistant-audio-player[data-message-id="${String(messageId)}"]`
    : '.assistant-audio-player';
  const matches = Array.from(document.querySelectorAll(selector));
  return matches.at(-1) || null;
};

const applyReplyPayloadFromMessage = (message, durationOverride = 0) => {
  if (!message?.content) {
    assistantReplyPayload.value = null;
    replySync.profile = null;
    return;
  }

  const resolvedDuration = Math.max(Number(durationOverride) || estimateReplyDuration(message.content), 0.8);
  const profile = inferAssistantReplyProfile(message.content);

  replySync.duration = resolvedDuration;
  replySync.profile = profile;
  assistantReplyPayload.value = buildAssistantReplyPayload({
    text: message.content,
    duration: resolvedDuration,
    profile,
  });
};

const startReplyMonitor = () => {
  stopReplyMonitor();
  if (!replyAudio || !replyAnalyser || !replyAnalyserBuffer) return;

  const updateFrame = () => {
    if (!replyAudio || !replyAnalyser || !replyAnalyserBuffer) return;

    replyAnalyser.getByteTimeDomainData(replyAnalyserBuffer);
    let energy = 0;
    for (let index = 0; index < replyAnalyserBuffer.length; index += 1) {
      const sample = (replyAnalyserBuffer[index] - 128) / 128;
      energy += sample * sample;
    }

    const rms = Math.sqrt(energy / replyAnalyserBuffer.length);
    replySync.currentTime = Number.isFinite(replyAudio.currentTime) ? replyAudio.currentTime : 0;
    replySync.duration = Number.isFinite(replyAudio.duration) ? replyAudio.duration : replySync.duration;
    replySync.mouthLevel = clamp((rms - 0.008) * 8.5, 0, 1);
    replyMonitorFrameId = window.requestAnimationFrame(updateFrame);
  };

  updateFrame();
};

const ensureReplyAudioGraph = async (audioElement) => {
  if (!audioElement) return;

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  if (!replyAudioContext || replyAudioContext.state === 'closed') {
    replyAudioContext = new AudioContextClass();
  }

  if (replySourceElement !== audioElement) {
    if (replySourceNode) {
      replySourceNode.disconnect();
      replySourceNode = null;
    }
    if (replyAnalyser) {
      replyAnalyser.disconnect();
      replyAnalyser = null;
    }

    replyAnalyser = replyAudioContext.createAnalyser();
    replyAnalyser.fftSize = 1024;
    replyAnalyser.smoothingTimeConstant = 0.58;
    replyAnalyserBuffer = new Uint8Array(replyAnalyser.fftSize);
    replySourceNode = replyAudioContext.createMediaElementSource(audioElement);
    replySourceNode.connect(replyAnalyser);
    replyAnalyser.connect(replyAudioContext.destination);
    replySourceElement = audioElement;
  }

  if (replyAudioContext.state === 'suspended') {
    await replyAudioContext.resume();
  }
};

const bindReplyAudioElement = async (audioElement) => {
  if (!audioElement || !isAssistantAudioElement(audioElement)) return;

  replyAudio = audioElement;
  const messageId = audioElement.dataset.messageId || '';
  const message = findAssistantReplyMessage(messageId);
  if (message) {
    activeReplyMessage.value = message;
    replySync.messageId = String(message.id);
    applyReplyPayloadFromMessage(message, audioElement.duration);
  }

  await ensureReplyAudioGraph(audioElement);
};

const stopAssistantReply = ({ clearPayload = false } = {}) => {
  stopReplyMonitor();

  if (replyAudio) {
    replyAudio.pause();
    if (replyAudio.currentTime) {
      replyAudio.currentTime = 0;
    }
  }

  resetReplySync({ clearPayload });
};

const playAssistantReply = async (message) => {
  if (!message?.id || !isPlayableAudioUrl(message.audioUrl)) return;

  stopAssistantReply();
  activeReplyMessage.value = message;
  replySync.messageId = String(message.id);
  latestAutoPlayedReplyId.value = String(message.id);
  applyReplyPayloadFromMessage(message);

  try {
    await nextTick();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    const audio = getAssistantAudioElement(message.id);
    if (!audio) {
      throw new Error('Assistant audio element not found.');
    }
    if (!audio.getAttribute('src')) {
      audio.src = resolveMediaUrl(message.audioUrl);
    }
    await bindReplyAudioElement(audio);
    await audio.play();
  } catch (error) {
    console.warn('Assistant reply autoplay was blocked or failed.', error);
    resetReplySync({ clearPayload: true });
  }
};

const handleReplyAudioPlay = async (event) => {
  const audioElement = event.target;
  if (!isAssistantAudioElement(audioElement)) return;

  await bindReplyAudioElement(audioElement);
  replySync.active = true;
  replySync.isPlaying = true;
  replySync.currentTime = Number.isFinite(audioElement.currentTime) ? audioElement.currentTime : 0;
  replySync.duration = Number.isFinite(audioElement.duration) ? audioElement.duration : replySync.duration;
  startReplyMonitor();
};

const handleReplyAudioPause = (event) => {
  const audioElement = event.target;
  if (!isAssistantAudioElement(audioElement) || audioElement !== replyAudio) return;

  replySync.isPlaying = false;
  if (!audioElement.ended) {
    replySync.active = false;
    replySync.mouthLevel = 0;
    stopReplyMonitor();
  }
};

const handleReplyAudioEnded = (event) => {
  const audioElement = event.target;
  if (!isAssistantAudioElement(audioElement) || audioElement !== replyAudio) return;
  resetReplySync({ clearPayload: true });
};

const handleReplyAudioLoadedMetadata = (event) => {
  const audioElement = event.target;
  if (!isAssistantAudioElement(audioElement)) return;
  const message = findAssistantReplyMessage(audioElement.dataset.messageId || '');
  if (message) {
    applyReplyPayloadFromMessage(message, audioElement.duration);
  }
};

const handleReplyAudioError = (event) => {
  const audioElement = event.target;
  if (!isAssistantAudioElement(audioElement) || audioElement !== replyAudio) return;
  console.warn('Assistant reply audio playback failed.', audioElement.error);
  resetReplySync({ clearPayload: true });
};

const stateMode = computed(() => {
  if (props.sending) return 'listening';
  if (replySync.active || replySync.isPlaying) return 'responding';
  if (isRecentlyAnswered.value) return 'responding';
  if (analysisMode.value === 'full_multimodal' && effectiveLive2dPayload.value?.parameter_frames?.length) return 'listening';
  if (props.haruLoading) return 'listening';
  if (analysisMode.value === 'partial_media') return 'listening';
  return 'idle';
});

const statusLabel = computed(() => {
  if (props.sending) return '倾听中';
  if (stateMode.value === 'responding') return '回答中';
  if (props.haruLoading) return '倾听中';
  if (stateMode.value === 'listening') return '倾听中';
  if (analysisMode.value === 'analysis_error') return '分析失败';
  return '待机中';
});

watch(
  () => props.sending,
  (sending) => {
    if (sending) {
      allowNextAssistantAutoplay.value = true;
    }
  },
);

watch(
  () => latestAssistantMessage.value?.id ?? '',
  async (nextId) => {
    const message = latestAssistantMessage.value;

    if (!assistantHistoryHydrated.value) {
      assistantHistoryHydrated.value = true;
      latestAutoPlayedReplyId.value = nextId ? String(nextId) : '';
      return;
    }

    if (!nextId) {
      latestAutoPlayedReplyId.value = '';
      stopAssistantReply({ clearPayload: true });
      return;
    }

    if (message?.isPending) {
      return;
    }

    if (!allowNextAssistantAutoplay.value) {
      latestAutoPlayedReplyId.value = String(nextId);
      stopAssistantReply({ clearPayload: true });
      return;
    }

    allowNextAssistantAutoplay.value = false;

    if (!message || !isPlayableAudioUrl(message.audioUrl)) {
      latestAutoPlayedReplyId.value = String(nextId);
      stopAssistantReply({ clearPayload: true });
      return;
    }

    if (String(nextId) === latestAutoPlayedReplyId.value) {
      return;
    }

    await playAssistantReply(message);
  },
  { flush: 'post' },
);

onBeforeUnmount(async () => {
  stopAssistantReply({ clearPayload: true });
  document.removeEventListener('play', handleReplyAudioPlay, true);
  document.removeEventListener('pause', handleReplyAudioPause, true);
  document.removeEventListener('ended', handleReplyAudioEnded, true);
  document.removeEventListener('loadedmetadata', handleReplyAudioLoadedMetadata, true);
  document.removeEventListener('error', handleReplyAudioError, true);
  if (replyAudioContext && replyAudioContext.state !== 'closed') {
    await replyAudioContext.close();
  }
  replyAudioContext = null;
  replyAnalyser = null;
  replySourceNode = null;
  replySourceElement = null;
  replyAnalyserBuffer = null;
  replyAudio = null;
});

onMounted(() => {
  document.addEventListener('play', handleReplyAudioPlay, true);
  document.addEventListener('pause', handleReplyAudioPause, true);
  document.addEventListener('ended', handleReplyAudioEnded, true);
  document.addEventListener('loadedmetadata', handleReplyAudioLoadedMetadata, true);
  document.addEventListener('error', handleReplyAudioError, true);
});
</script>

<style scoped>
.digital-panel {
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 14px;
  padding: 18px;
  background:
    radial-gradient(circle at top left, rgba(220, 236, 248, 0.82), transparent 28%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.86), rgba(245, 249, 246, 0.76));
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-title-block {
  display: grid;
  gap: 6px;
}

.panel-tag {
  color: var(--brand-deep);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.panel-title-block h1 {
  margin: 0;
  color: var(--text-main);
  font-size: clamp(1.35rem, 2.4vw, 2rem);
  line-height: 1.1;
}

.status-chip,
.meta-chip {
  border-radius: 999px;
  background: rgba(220, 236, 248, 0.92);
  color: var(--text-main);
  font-size: 0.8rem;
  padding: 0.42rem 0.78rem;
}

.live2d-stage {
  min-height: 0;
  height: 100%;
}

.stage-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 28px;
  color: var(--text-soft);
  background:
    radial-gradient(circle at 50% 24%, rgba(255, 255, 255, 0.9), transparent 34%),
    linear-gradient(180deg, #dceaf7 0%, #eef6f1 100%);
}

.panel-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.meta-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
