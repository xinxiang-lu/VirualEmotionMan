<template>
  <section class="message-list card-surface">
    <div v-if="!messages.length" class="empty-state">开始和心陪陪聊聊吧</div>
    <div v-else ref="scrollContainer" class="message-scroll">
      <article
        v-for="message in messages"
        :key="message.id"
        :class="[
          'message-item',
          message.sender === 'user' ? 'is-user' : 'is-assistant',
          message.isPending ? 'is-pending' : '',
        ]"
        >
          <span class="sender">{{ message.senderLabel }}</span>
          <div class="bubble">
            <p>{{ getDisplayContent(message) }}</p>

            <div v-if="message.audioUrl || message.videoUrl" class="media-meta">
              <audio
                v-if="isPlayableAudio(message.audioUrl)"
                :class="['audio-player', message.sender === 'assistant' ? 'assistant-audio-player' : 'user-audio-player']"
                :data-message-id="message.id"
                :data-sender="message.sender"
                :src="resolveMediaUrl(message.audioUrl)"
                controls
                preload="none"
              />
              <span v-if="message.audioUrl" class="media-pill">含音频</span>
              <span v-if="message.videoUrl" class="media-pill">含视频</span>
            </div>
            <time>{{ message.time }}</time>
          </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue';
import { resolveMediaUrl } from '@/utils/mediaUrl';

const props = defineProps({ messages: { type: Array, default: () => [] } });
const scrollContainer = ref(null);

const getDisplayContent = (message) => {
  const content = (message.content || '').trim();
  if (content) return content;

  const hasAudio = Boolean(message.audioUrl);
  const hasVideo = Boolean(message.videoUrl);

  if (hasAudio && hasVideo) return '已发送语音和视频输入';
  if (hasAudio) return '已发送语音输入';
  if (hasVideo) return '已发送视频输入';
  return '已发送消息';
};

const isPlayableAudio = (audioUrl) => Boolean(audioUrl && !String(audioUrl).startsWith('__pending__'));

const scrollToBottom = async () => {
  await nextTick();
  if (!scrollContainer.value) return;
  scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight;
};

watch(
  () =>
    props.messages
      .map((message) => [
        message.id,
        message.time,
        message.isPending ? 1 : 0,
        message.audioUrl ? 1 : 0,
        message.videoUrl ? 1 : 0,
        (message.content || '').trim(),
      ].join(':'))
      .join('|'),
  () => {
    scrollToBottom();
  },
  { immediate: true, flush: 'post' },
);
</script>

<style scoped>
.message-list { width:100%; height:100%; min-height:0; overflow:hidden; padding:18px; }
.empty-state, .message-scroll { height:100%; }
.empty-state { display:flex; align-items:center; justify-content:center; color:var(--text-soft); text-align:center; }
.message-scroll { overflow:auto; display:grid; align-content:start; gap:14px; }
.message-item { display:grid; gap:6px; }
.message-item.is-user { justify-items:end; }
.message-item.is-assistant { justify-items:start; }
.message-item.is-pending .sender { opacity:.72; }
.sender { color:var(--text-soft); font-size:.82rem; }
.bubble { max-width:min(100%, 360px); padding:14px 16px; border-radius:20px; background:rgba(255,255,255,.78); }
.message-item.is-user .bubble { background:linear-gradient(135deg, rgba(222,236,248,.96), rgba(219,237,229,.94)); }
.message-item.is-pending .bubble { border:1px dashed rgba(104,132,146,.38); }
.bubble p { margin:0; color:var(--text-main); line-height:1.75; white-space:pre-wrap; }
.media-meta { margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; }
.audio-player { width:min(100%, 280px); }
.media-pill { padding:.3rem .62rem; border-radius:999px; font-size:.76rem; }
.media-pill { background:rgba(239,244,248,.96); color:var(--text-soft); }
.bubble time { display:block; margin-top:8px; color:var(--text-soft); font-size:.78rem; }
</style>

