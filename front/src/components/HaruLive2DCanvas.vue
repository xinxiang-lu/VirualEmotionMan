<template>
  <div class="haru-stage">
    <div ref="stageRef" class="stage-canvas-host"></div>
    <div v-if="statusText" class="stage-overlay">
      <span>{{ statusText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Live2DPlayer } from '@/utils/haruLive2dPlayer';
import { getLive2dModelConfig, normalizeLive2dModelCode } from '@/config/live2dModels';

const props = defineProps({
  payload: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  modelCode: { type: String, default: 'haru' },
  modelLabel: { type: String, default: '' },
  replySync: { type: Object, default: null },
  stateMode: { type: String, default: 'idle' },
});

const stageRef = ref(null);
const player = ref(null);
const modelReady = ref(false);
const loadError = ref('');
let mountToken = 0;

const resolvedModelCode = computed(() => normalizeLive2dModelCode(props.modelCode));
const resolvedModelLabel = computed(() => props.modelLabel || getLive2dModelConfig(resolvedModelCode.value).label);

const statusText = computed(() => {
  if (loadError.value) return `${resolvedModelLabel.value} 加载失败：${loadError.value}`;
  if (!modelReady.value) return `正在加载 ${resolvedModelLabel.value} 模型...`;
  if (props.loading) return `正在整理 ${resolvedModelLabel.value} 的驱动参数...`;
  return '';
});

const syncPlayer = () => {
  if (!player.value || !modelReady.value) return;
  player.value.setMode(props.stateMode || 'idle');
  player.value.setReplySync(props.replySync);
  if (props.payload?.parameter_frames?.length) {
    player.value.setPayload(props.payload);
  } else {
    player.value.clearPayload();
  }
};

const mountPlayer = async () => {
  const token = ++mountToken;

  if (!stageRef.value) return;

  modelReady.value = false;
  loadError.value = '';
  player.value?.destroy();
  player.value = null;

  try {
    await nextTick();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    if (token !== mountToken) return;

    player.value = new Live2DPlayer(stageRef.value, {
      modelCode: resolvedModelCode.value,
      presentationMode: props.stateMode || 'idle',
    });
    await player.value.init();

    if (token !== mountToken) {
      player.value?.destroy();
      player.value = null;
      return;
    }

    modelReady.value = true;
    syncPlayer();
  } catch (error) {
    if (token !== mountToken) return;
    console.error(error);
    loadError.value = error?.message || '未知错误';
  }
};

watch(
  () => props.payload,
  () => {
    syncPlayer();
  },
  { deep: false },
);

watch(
  () => props.stateMode,
  () => {
    syncPlayer();
  },
);

watch(
  () => props.replySync,
  () => {
    syncPlayer();
  },
);

watch(
  () => resolvedModelCode.value,
  async () => {
    await mountPlayer();
  },
);

onMounted(async () => {
  await mountPlayer();
});

onBeforeUnmount(() => {
  mountToken += 1;
  player.value?.destroy();
  player.value = null;
});
</script>

<style scoped>
.haru-stage {
  position: relative;
  min-height: 360px;
  border-radius: 28px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 24%, rgba(255, 255, 255, 0.9), transparent 34%),
    linear-gradient(180deg, #dceaf7 0%, #eef6f1 100%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.52);
}

.stage-canvas-host {
  width: 100%;
  height: 100%;
  min-height: 360px;
}

.stage-canvas-host :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.stage-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: var(--text-main);
  font-weight: 600;
  text-align: center;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.14));
  pointer-events: none;
}
</style>
