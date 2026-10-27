<template>
  <section class="auth-layout">
    <article class="auth-card card-surface">
      <div v-if="badge || switchText" class="auth-topline">
        <span v-if="badge" class="badge">{{ badge }}</span>
        <RouterLink v-if="switchTo" class="switch-link" :to="switchTo">
          {{ switchText }}
        </RouterLink>
      </div>

      <div class="auth-header">
        <h1>{{ title }}</h1>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>

      <div class="auth-body">
        <slot />
      </div>

      <div v-if="$slots.footer" class="auth-footer">
        <slot name="footer" />
      </div>
    </article>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router';

defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  badge: {
    type: String,
    default: '',
  },
  switchText: {
    type: String,
    default: '',
  },
  switchTo: {
    type: [String, Object],
    default: '',
  },
});
</script>

<style scoped>
.auth-layout {
  min-height: calc(100vh - 156px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 0 20px;
}

.auth-card {
  width: min(560px, 100%);
  padding: 28px;
}

.auth-topline,
.auth-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.auth-header {
  margin-top: 20px;
}

.auth-header h1 {
  margin: 0;
  color: var(--text-main);
  font-size: clamp(1.7rem, 3vw, 2.3rem);
}

.auth-header p {
  margin: 12px 0 0;
  color: var(--text-soft);
  line-height: 1.7;
}

.auth-body {
  margin-top: 24px;
}

.auth-footer {
  margin-top: 22px;
  color: var(--text-soft);
}

.badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.5rem 0.85rem;
  background: rgba(216, 233, 247, 0.8);
  color: var(--brand-deep);
  font-size: 0.9rem;
}

.switch-link {
  color: var(--brand-deep);
  font-weight: 600;
}

@media (max-width: 768px) {
  .auth-layout {
    min-height: auto;
    align-items: start;
  }

  .auth-card {
    padding: 22px;
  }
}
</style>
