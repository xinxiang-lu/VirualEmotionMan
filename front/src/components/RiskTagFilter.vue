<template>
  <div class="tag-filter">
    <button
      v-for="tag in tags"
      :key="tag"
      :class="['tag-chip', selectedTags.includes(tag) ? 'is-active' : '']"
      type="button"
      @click="$emit('toggle', tag)"
    >
      {{ tag }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  tags: { type: Array, default: () => [] },
  selectedTags: { type: Array, default: () => [] },
});

defineEmits(['toggle']);
</script>

<style scoped>
.tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tag-chip {
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  padding: 0.56rem 0.92rem;
  color: var(--text-soft);
}

.tag-chip.is-active {
  background: linear-gradient(135deg, rgba(222, 236, 248, 0.96), rgba(219, 237, 229, 0.94));
  color: var(--text-main);
  border-color: rgba(122, 158, 178, 0.24);
}
</style>
