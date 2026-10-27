<template>
  <header class="nav-shell">
    <div class="nav-inner">
      <RouterLink class="brand-mark" :to="{ name: 'home' }" aria-label="心陪陪首页">
        <span class="brand-logo">心</span>
      </RouterLink>

      <RouterLink class="project-name" :to="{ name: 'home' }">
        {{ APP_NAME }}
      </RouterLink>

      <div class="nav-actions">
        <template v-if="authStore.isAuthenticated">
          <span class="welcome-text">{{ authStore.displayName }}</span>
          <button class="ghost-button" type="button" @click="logout">退出</button>
        </template>
        <RouterLink v-else class="primary-button nav-login" :to="{ name: 'login' }">
          登录
        </RouterLink>
      </div>
    </div>
  </header>
</template>

<script setup>
import { RouterLink, useRouter } from 'vue-router';
import { APP_NAME } from '@/config';
import { useAuthStore } from '@/store/auth';

const authStore = useAuthStore();
const router = useRouter();

const logout = () => {
  authStore.logout();
  router.push({ name: 'home' });
};
</script>

<style scoped>
.nav-shell {
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(18px);
  background: rgba(250, 247, 241, 0.72);
  border-bottom: 1px solid var(--line-soft);
}

.nav-inner {
  width: min(1180px, calc(100% - 32px));
  min-height: 76px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
}

.brand-mark,
.nav-actions {
  display: flex;
  align-items: center;
}

.brand-mark {
  width: fit-content;
}

.brand-logo {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: linear-gradient(135deg, #bedcf7 0%, #cfe8d6 100%);
  color: var(--text-main);
  font-size: 1.15rem;
  font-weight: 700;
  box-shadow: 0 10px 24px rgba(126, 156, 167, 0.18);
}

.project-name {
  justify-self: center;
  font-size: clamp(1.15rem, 2vw, 1.45rem);
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-main);
}

.nav-actions {
  justify-self: end;
  gap: 12px;
}

.welcome-text {
  color: var(--text-soft);
  font-size: 0.95rem;
}

.nav-login {
  min-width: 0;
  padding: 0.68rem 1rem;
  line-height: 1;
  text-align: center;
}

@media (max-width: 768px) {
  .nav-inner {
    width: min(100%, calc(100% - 24px));
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "brand actions"
      "title title";
    padding: 12px 0;
  }

  .brand-mark {
    grid-area: brand;
  }

  .project-name {
    grid-area: title;
    justify-self: start;
  }

  .nav-actions {
    grid-area: actions;
  }
}
</style>


