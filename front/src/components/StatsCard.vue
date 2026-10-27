<template>
  <article :class="['stats-card', toneClass]">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: String, default: '' },
  tone: { type: String, default: 'blue' },
});

const toneClass = computed(() => `tone-${props.tone}`);
</script>

<style scoped>
.stats-card {
  border-radius: 22px;
  padding: 18px;
  background: rgba(255, 255, 255, 0.74);
  display: grid;
  gap: 12px;
}

.stats-card span {
  color: var(--text-soft);
  font-size: 0.9rem;
}

.stats-card strong {
  color: var(--text-main);
  font-size: 1.5rem;
}

.tone-blue {
  background: linear-gradient(180deg, rgba(226, 238, 248, 0.86), rgba(255, 255, 255, 0.82));
}

.tone-green {
  background: linear-gradient(180deg, rgba(225, 241, 232, 0.9), rgba(255, 255, 255, 0.82));
}

.tone-purple {
  background: linear-gradient(180deg, rgba(236, 230, 248, 0.9), rgba(255, 255, 255, 0.82));
}

.tone-orange {
  background: linear-gradient(180deg, rgba(248, 236, 222, 0.92), rgba(255, 255, 255, 0.82));
}
</style>
