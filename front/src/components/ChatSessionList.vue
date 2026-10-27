<template>
  <section class="session-list card-surface">
    <div class="list-header">
      <h2>你的聊天</h2>
      <span>{{ sessions.length }} 个会话</span>
    </div>
    <div class="list-body">
      <div v-if="!sessions.length" class="empty-state">
        <strong>还没有聊天会话</strong>
        <p>点一下“新聊天”，我们就可以从这里开始。</p>
      </div>
      <article
        v-for="session in sessions"
        :key="session.id"
        :class="['session-item', session.id === activeSessionId ? 'is-active' : '']"
      >
        <button class="session-main" type="button" @click="$emit('select', session.id)">
          <div class="session-top">
            <strong>{{ session.title }}</strong>
            <span>{{ session.updatedAt }}</span>
          </div>
          <p>{{ session.preview }}</p>
        </button>
        <div class="session-actions">
          <button class="action-button" type="button" @click="$emit('rename', session)">改名</button>
          <button class="action-button danger" type="button" @click="$emit('delete', session)">删除</button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
  activeSessionId: { type: [String, Number], default: '' },
});
defineEmits(['select', 'rename', 'delete']);
</script>

<style scoped>
.session-list { padding: 18px; display: flex; flex-direction: column; min-height: 0; height: 100%; }
.list-header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
.list-header h2 { margin:0; font-size:1rem; color:var(--text-main); }
.list-header span { color:var(--text-soft); font-size:.85rem; }
.list-body { display:grid; gap:12px; overflow:auto; flex:1; min-height:0; align-content:start; padding-right:4px; }
.empty-state { min-height:180px; border-radius:20px; background:linear-gradient(180deg, rgba(224,237,248,.72), rgba(241,246,242,.7)); display:grid; place-items:center; text-align:center; padding:18px; }
.empty-state strong { color:var(--text-main); font-size:.98rem; }
.empty-state p { margin:8px 0 0; color:var(--text-soft); line-height:1.7; }
.session-item { border:1px solid transparent; border-radius:18px; background:rgba(255,255,255,.68); padding:14px; display:grid; gap:12px; }
.session-item.is-active { border-color:rgba(122,158,178,.3); background:rgba(224,237,248,.82); }
.session-main { border:none; background:transparent; padding:0; text-align:left; display:grid; gap:8px; }
.session-top { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.session-top strong { color:var(--text-main); font-size:.95rem; }
.session-top span, .session-item p { color:var(--text-soft); font-size:.84rem; }
.session-item p { margin:8px 0 0; line-height:1.6; }
.session-actions { display:flex; justify-content:end; gap:8px; }
.action-button { border:1px solid var(--line-soft); border-radius:999px; background:rgba(255,255,255,.86); padding:.35rem .72rem; color:var(--text-soft); font-size:.78rem; }
.action-button.danger { color:#b45858; }
</style>
