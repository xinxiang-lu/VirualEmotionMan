<template>
  <section class="intervention-page">
    <aside class="left-panel">
      <article class="card-surface info-card">
        <div class="section-head">
          <p class="eyebrow">人工介入对象</p>
          <RouterLink class="back-link" :to="{ name: 'admin-dashboard' }">返回管理员工作台</RouterLink>
        </div>
        <h1>{{ currentUser.name }}</h1>
        <dl class="info-grid">
          <div>
            <dt>手机号</dt>
            <dd>{{ currentUser.account }}</dd>
          </div>
          <div>
            <dt>性别</dt>
            <dd>{{ currentUser.gender }}</dd>
          </div>
          <div>
            <dt>年龄</dt>
            <dd>{{ currentUser.age }} 岁</dd>
          </div>
          <div>
            <dt>风险程度</dt>
            <dd :class="['risk-badge', riskToneClass]">{{ currentUser.riskLevel }}</dd>
          </div>
        </dl>
        <div class="tag-row">
          <span v-for="tag in currentUser.tags" :key="tag" class="soft-tag">{{ tag }}</span>
        </div>
      </article>

      <article class="card-surface note-card">
        <p class="eyebrow">介入说明</p>
        <p class="note-text">{{ session.interventionNote }}</p>
      </article>

      <article class="card-surface action-card">
        <button class="primary-button end-button" type="button" @click="finishIntervention">
          结束人工介入
        </button>
      </article>
    </aside>

    <section class="right-panel">
      <article class="card-surface message-card">
        <header class="message-header">
          <div>
            <p class="eyebrow">人工接管会话</p>
            <h2>以“心陪陪”身份继续陪伴</h2>
          </div>
          <span class="status-pill">人工接管中</span>
        </header>

        <div ref="messageListRef" class="message-list">
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['message-row', `message-row--${message.sender}`]"
          >
            <div :class="['message-bubble', `message-bubble--${message.sender}`]">
              <div class="message-meta">
                <strong>{{ message.name }}</strong>
                <span>{{ message.time }}</span>
              </div>
              <p>{{ message.content }}</p>
            </div>
          </div>
        </div>
      </article>

      <article class="card-surface composer-card">
        <textarea
          v-model="draft"
          class="composer-textarea"
          rows="4"
          placeholder="以“心陪陪”身份输入回复内容"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <div class="composer-actions">
          <p>按 Enter 发送，Shift + Enter 换行</p>
          <button class="primary-button" type="button" @click="sendMessage">发送回复</button>
        </div>
      </article>
    </section>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { createIntervention, fetchInterventionByUser, finishIntervention as finishInterventionRequest, sendInterventionMessage } from '@/api/admin';
import { getRealtimeSocket, joinConversationRoom, leaveConversationRoom } from '@/services/realtime';
import { RouterLink, useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();
const draft = ref('');
const messageListRef = ref(null);
const session = ref({
  id: null,
  interventionNote: '',
  status: 'active',
  user: {
    name: '',
    account: '',
    gender: '',
    age: '',
    riskCode: null,
    riskLevel: '尚未评估',
    tags: [],
  },
  messages: [],
});
const messages = ref([]);
let realtimeSocket = null;
let joinedConversationId = '';
const handledRealtimeEventKeys = new Set();

const currentUser = computed(() => session.value.user || { tags: [] });
const currentRiskCode = computed(() => {
  if (currentUser.value.riskCode) return currentUser.value.riskCode;
  if (currentUser.value.riskLevel === '高') return 'high';
  if (currentUser.value.riskLevel === '中') return 'medium';
  if (currentUser.value.riskLevel === '低') return 'low';
  return null;
});

const riskToneClass = computed(() => {
  if (currentRiskCode.value === 'high' || currentRiskCode.value === 'critical') return 'risk-badge--high';
  if (currentRiskCode.value === 'medium') return 'risk-badge--medium';
  if (currentRiskCode.value === 'low') return 'risk-badge--low';
  return 'risk-badge--unassessed';
});

const normalizeMessages = (items = []) =>
  items.map((message) => ({
    ...message,
    name: message.senderLabel || message.name || '',
  }));

const upsertMessages = async (items = []) => {
  const nextMessages = Array.isArray(items) ? items.filter(Boolean) : [items].filter(Boolean);
  if (!nextMessages.length) return;
  const current = messages.value || [];
  const byId = new Map(current.map((message) => [String(message.id), message]));
  nextMessages.forEach((message) => {
    byId.set(String(message.id), {
      ...message,
      name: message.senderLabel || message.name || '',
    });
  });
  const existingIds = new Set(current.map((message) => String(message.id)));
  const appended = nextMessages
    .filter((message) => !existingIds.has(String(message.id)))
    .map((message) => byId.get(String(message.id)));
  messages.value = [
    ...current.map((message) => byId.get(String(message.id)) || message),
    ...appended,
  ];
  await scrollMessagesToLatest('smooth');
};

const joinInterventionConversation = () => {
  const conversationId = session.value?.conversationId || session.value?.conversation_id || session.value?.conversation?.id;
  if (!conversationId || joinedConversationId === conversationId) return;
  if (joinedConversationId) {
    leaveConversationRoom(joinedConversationId);
  }
  joinConversationRoom(conversationId);
  joinedConversationId = conversationId;
};

const setupRealtime = () => {
  realtimeSocket = getRealtimeSocket();
  if (!realtimeSocket) return;
  realtimeSocket.off('message:new');
  realtimeSocket.off('intervention:ended');
  realtimeSocket.on('message:new', (payload = {}) => {
    const sessionConversationId = session.value?.conversationId || session.value?.conversation_id || session.value?.conversation?.id;
    if (String(payload.conversationId) !== String(sessionConversationId)) return;
    void upsertMessages(payload.message);
  });
  realtimeSocket.on('intervention:ended', (payload = {}) => {
    if (String(payload.session?.id) !== String(session.value?.id)) return;
    const eventKey = `intervention:ended:${payload.session?.id}`;
    if (handledRealtimeEventKeys.has(eventKey)) return;
    handledRealtimeEventKeys.add(eventKey);
    session.value = payload.session || session.value;
    window.alert('本次人工介入已结束。');
  });
};

const scrollMessagesToLatest = async (behavior = 'auto') => {
  await nextTick();
  const list = messageListRef.value;
  if (!list) return;
  list.scrollTo({ top: list.scrollHeight, behavior });
};

const loadInterventionSession = async () => {
  try {
    let data;
    try {
      data = await fetchInterventionByUser(route.params.userId);
    } catch (error) {
      if (error?.status === 404) {
        data = await createIntervention({ user_id: Number(route.params.userId) });
      } else {
        throw error;
      }
    }

    session.value = data.session || session.value;
    messages.value = normalizeMessages(session.value.messages || []);
    joinInterventionConversation();
    await scrollMessagesToLatest();
  } catch (error) {
    window.alert(error?.message || '人工介入会话加载失败，请稍后再试。');
    router.push({ name: 'admin-dashboard' });
  }
};

const sendMessage = async () => {
  const content = draft.value.trim();
  if (!content) return;

  try {
    const data = await sendInterventionMessage(session.value.id, content);
    await upsertMessages(data.chat_message);
    draft.value = '';
  } catch (error) {
    window.alert(error?.message || '人工回复发送失败，请稍后再试。');
  }
};

const finishIntervention = async () => {
  try {
    await finishInterventionRequest(session.value.id);
    router.push({ name: 'admin-dashboard' });
  } catch (error) {
    window.alert(error?.message || '结束人工介入失败，请稍后再试。');
  }
};

onMounted(() => {
  setupRealtime();
  loadInterventionSession();
});

onBeforeUnmount(() => {
  if (joinedConversationId) {
    leaveConversationRoom(joinedConversationId);
    joinedConversationId = '';
  }
  if (realtimeSocket) {
    realtimeSocket.off('message:new');
    realtimeSocket.off('intervention:ended');
  }
});
</script>

<style scoped>
.intervention-page {
  height: calc(100vh - 132px);
  max-height: calc(100vh - 132px);
  min-height: calc(100vh - 132px);
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(280px, 2.2fr) minmax(0, 7.8fr);
  gap: 18px;
}

.left-panel,
.right-panel {
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: grid;
  gap: 16px;
}

.left-panel {
  align-content: start;
}

.right-panel {
  grid-template-rows: minmax(0, 1fr) auto;
}

.info-card,
.note-card,
.action-card,
.message-card,
.composer-card {
  padding: 22px;
}

.section-head,
.message-header,
.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-head {
  align-items: flex-start;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--brand-deep);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
}

.back-link {
  color: var(--text-soft);
  font-size: 0.92rem;
}

.info-card h1,
.message-header h2 {
  margin: 0;
  color: var(--text-main);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
}

.info-grid div {
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.7);
}

.info-grid dt {
  margin-bottom: 8px;
  color: var(--text-soft);
  font-size: 0.82rem;
}

.info-grid dd {
  margin: 0;
  color: var(--text-main);
  font-weight: 600;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.soft-tag {
  border-radius: 999px;
  padding: 0.38rem 0.72rem;
  background: rgba(227, 238, 247, 0.8);
  color: var(--brand-deep);
  font-size: 0.82rem;
}

.risk-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.5rem;
  border-radius: 999px;
  padding: 0.28rem 0.68rem;
}

.risk-badge--high {
  color: #9c4d4e;
  background: rgba(236, 202, 198, 0.85);
}

.risk-badge--medium {
  color: #9b6f3e;
  background: rgba(245, 221, 186, 0.88);
}

.risk-badge--low {
  color: #497e61;
  background: rgba(196, 229, 210, 0.88);
}

.risk-badge--unassessed {
  color: #4e5a63;
  background: rgba(214, 219, 226, 0.9);
}

.note-text {
  margin: 0;
  color: var(--text-soft);
  line-height: 1.85;
}

.end-button {
  width: 100%;
  justify-content: center;
}

.message-card {
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.status-pill {
  border-radius: 999px;
  padding: 0.36rem 0.76rem;
  background: rgba(214, 236, 226, 0.9);
  color: #4d7a69;
  font-size: 0.82rem;
}

.message-list {
  margin-top: 18px;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  display: grid;
  gap: 16px;
  padding-right: 6px;
}

.message-row {
  display: flex;
}

.message-row--user {
  justify-content: flex-start;
}

.message-row--ai,
.message-row--assistant,
.message-row--human {
  justify-content: flex-end;
}

.message-bubble {
  width: min(100%, 560px);
  border-radius: 24px;
  padding: 16px 18px;
}

.message-bubble--user {
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--line-soft);
}

.message-bubble--ai,
.message-bubble--assistant {
  background: rgba(224, 237, 247, 0.9);
}

.message-bubble--human {
  background: rgba(212, 236, 223, 0.92);
}

.message-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-soft);
  font-size: 0.82rem;
}

.message-meta strong {
  color: var(--text-main);
}

.message-bubble p {
  margin: 10px 0 0;
  color: var(--text-main);
  line-height: 1.8;
  white-space: pre-wrap;
}

.composer-textarea {
  width: 100%;
  resize: none;
  border: 1px solid var(--line-soft);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.84);
  padding: 16px 18px;
  color: var(--text-main);
  outline: none;
}

.composer-actions {
  margin-top: 14px;
}

.composer-actions p {
  margin: 0;
  color: var(--text-soft);
  font-size: 0.88rem;
}

@media (max-width: 1100px) {
  .intervention-page {
    height: auto;
    max-height: none;
    min-height: 0;
    overflow: visible;
    grid-template-columns: 1fr;
  }

  .right-panel {
    grid-template-rows: 1fr auto;
  }
}

@media (max-width: 680px) {
  .info-grid {
    grid-template-columns: 1fr;
  }

  .message-header,
  .composer-actions,
  .section-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .message-bubble {
    width: 100%;
  }
}
</style>

