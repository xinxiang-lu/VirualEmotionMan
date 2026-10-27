<template>
  <div class="app-shell">
    <NavBar />
    <main
      :class="[
        'app-main',
        route.meta?.workspace ? 'workspace-main' : '',
        route.name === 'home' ? 'home-main' : '',
      ]"
    >
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { RouterView, useRoute } from 'vue-router';
import NavBar from '@/components/NavBar.vue';

const route = useRoute();
</script>

<style scoped>
.app-shell { min-height: 100vh; }
.app-main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 48px; }
.app-main.home-main { min-height: calc((100dvh - 76px) * 0.8); padding: 50px 0 0; display: flex; }
.app-main.workspace-main { width: min(1440px, calc(100% - 24px)); padding-bottom: 24px; }
@media (max-width: 768px) {
  .app-main { width: min(100%, calc(100% - 24px)); padding-top: 16px; padding-bottom: 32px; }
  .app-main.home-main { min-height: calc((100dvh - 112px) * 0.8); padding: 14px 0 0; }
}
</style>
