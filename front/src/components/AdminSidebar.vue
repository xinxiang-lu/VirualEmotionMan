<template>
  <aside class="admin-sidebar card-surface">
    <div class="sidebar-top">
      <h2>管理员工作台</h2>
      <p>围绕用户风险、人工介入和系统运行做统一管理。</p>
    </div>

    <nav class="menu-list">
      <button
        v-for="item in items"
        :key="item.key"
        :class="['menu-item', activeKey === item.key ? 'is-active' : '']"
        type="button"
        @click="$emit('select', item.key)"
      >
        <span class="menu-icon">{{ item.icon }}</span>
        <span class="menu-label">{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-bottom">
      <div class="admin-meta">
        <span class="avatar">{{ displayName.slice(0, 1) }}</span>
        <div>
          <strong>{{ displayName }}</strong>
          <span>管理员身份</span>
        </div>
      </div>
      <button class="ghost-button logout-button" type="button" @click="$emit('logout')">退出登录</button>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  activeKey: { type: String, default: '' },
  displayName: { type: String, default: '管理员' },
});

defineEmits(['select', 'logout']);
</script>

<style scoped>
.admin-sidebar {
  height: 100%;
  padding: 18px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
}

.sidebar-top h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 1.18rem;
}

.sidebar-top p {
  margin: 10px 0 0;
  color: var(--text-soft);
  line-height: 1.7;
  font-size: 0.9rem;
}

.menu-list {
  display: grid;
  gap: 10px;
  align-content: start;
}

.menu-item {
  border: 1px solid transparent;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
}

.menu-item.is-active {
  background: linear-gradient(135deg, rgba(222, 236, 248, 0.96), rgba(219, 237, 229, 0.94));
  border-color: rgba(122, 158, 178, 0.26);
}

.menu-icon {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(224, 235, 246, 0.85);
  color: var(--brand-deep);
  font-size: 0.9rem;
  font-weight: 700;
}

.menu-label {
  color: var(--text-main);
  font-weight: 600;
}

.sidebar-bottom {
  display: grid;
  gap: 14px;
}

.admin-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #c2dcf5, #d6ead9);
  color: var(--text-main);
  font-weight: 700;
}

.admin-meta strong {
  display: block;
  color: var(--text-main);
}

.admin-meta span:last-child {
  color: var(--text-soft);
  font-size: 0.84rem;
}

.logout-button {
  justify-content: center;
}
</style>
