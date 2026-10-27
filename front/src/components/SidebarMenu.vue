<template>
  <section class="sidebar-menu card-surface">
    <button
      v-for="item in items"
      :key="item.key"
      :class="['menu-item', activeKey === item.key ? 'is-active' : '']"
      type="button"
      @click="$emit('select', item.key)"
    >
      <span class="menu-title">{{ item.label }}</span>
      <span v-if="item.description" class="menu-desc">{{ item.description }}</span>
    </button>
  </section>
</template>

<script setup>
defineProps({ items: { type: Array, default: () => [] }, activeKey: { type: String, default: '' } });
defineEmits(['select']);
</script>

<style scoped>
.sidebar-menu { padding: 14px; display: grid; gap: 10px; }
.menu-item { border: 1px solid transparent; border-radius: 20px; background: rgba(255,255,255,.68); padding: 14px 16px; text-align: left; display: grid; gap: 6px; }
.menu-item.is-active { background: linear-gradient(135deg, rgba(220,235,248,.95), rgba(219,237,228,.92)); border-color: rgba(122,158,178,.28); }
.menu-title { color: var(--text-main); font-weight: 700; }
.menu-desc { color: var(--text-soft); font-size: .88rem; }
</style>
