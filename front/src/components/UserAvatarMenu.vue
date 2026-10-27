<template>
  <div ref="menuRoot" class="avatar-wrap">
    <button class="avatar-trigger card-surface" type="button" @click="toggleMenu">
      <span class="avatar-circle">
        <img v-if="avatarUrl" :src="avatarUrl" alt="用户头像" class="avatar-image" />
        <template v-else>{{ avatarText }}</template>
      </span>
      <div class="avatar-meta">
        <strong>{{ username }}</strong>
        <span>{{ subtitle }}</span>
      </div>
    </button>

    <div v-if="open" class="menu-popup card-surface">
      <button
        v-for="item in items"
        :key="item.key"
        class="menu-action"
        type="button"
        @click="handleSelect(item.key)"
      >
        {{ item.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

const props = defineProps({
  username: { type: String, default: '' },
  avatarUrl: { type: String, default: '' },
  subtitle: { type: String, default: '点击查看功能菜单' },
  items: { type: Array, default: () => [] },
});

const emit = defineEmits(['select']);

const open = ref(false);
const menuRoot = ref(null);

const avatarText = computed(() => props.username?.slice(0, 1) || '心');

const toggleMenu = () => {
  open.value = !open.value;
};

const handleSelect = (key) => {
  emit('select', key);
  open.value = false;
};

const handleOutsideClick = (event) => {
  if (!menuRoot.value?.contains(event.target)) {
    open.value = false;
  }
};

onMounted(() => document.addEventListener('click', handleOutsideClick));
onBeforeUnmount(() => document.removeEventListener('click', handleOutsideClick));
</script>

<style scoped>
.avatar-wrap {
  position: relative;
}

.avatar-trigger {
  width: 100%;
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.8);
}

.avatar-circle {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(135deg, #c2dcf5, #d6ead9);
  color: var(--text-main);
  font-weight: 700;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-meta {
  display: grid;
  text-align: left;
}

.avatar-meta strong {
  color: var(--text-main);
}

.avatar-meta span {
  color: var(--text-soft);
  font-size: 0.85rem;
}

.menu-popup {
  position: absolute;
  left: 0;
  bottom: calc(100% + 12px);
  width: 220px;
  padding: 10px;
  display: grid;
  gap: 6px;
  box-shadow: 0 22px 48px rgba(95, 114, 123, 0.18);
}

.menu-action {
  border: none;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  padding: 12px 14px;
  text-align: left;
  color: var(--text-main);
}
</style>

