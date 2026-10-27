<template>
  <section class="admin-dashboard">
    <AdminSidebar
      :items="adminMenuItems"
      :active-key="activeTab"
      :display-name="authStore.displayName"
      @select="activeTab = $event"
      @logout="handleLogout"
    />

    <div class="content-area">
      <UserManagement v-if="activeTab === 'users'" />
      <QuestionnaireManagement v-else-if="activeTab === 'questionnaires'" />
      <BusinessStats v-else-if="activeTab === 'business'" />
      <OpsStats v-else-if="activeTab === 'ops'" />
      <SystemSettings v-else />
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AdminSidebar from '@/components/AdminSidebar.vue';
import BusinessStats from '@/components/BusinessStats.vue';
import OpsStats from '@/components/OpsStats.vue';
import QuestionnaireManagement from '@/components/QuestionnaireManagement.vue';
import SystemSettings from '@/components/SystemSettings.vue';
import UserManagement from '@/components/UserManagement.vue';
import { adminMenuItems } from '@/mocks/adminMock';
import { useAuthStore } from '@/store/auth';

const authStore = useAuthStore();
const router = useRouter();
const activeTab = ref('users');

const handleLogout = () => {
  authStore.logout();
  router.push({ name: 'admin-login' });
};
</script>

<style scoped>
.admin-dashboard {
  min-height: calc(100vh - 132px);
  display: grid;
  grid-template-columns: minmax(220px, 2fr) minmax(0, 8fr);
  gap: 18px;
}

.content-area {
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1024px) {
  .admin-dashboard {
    grid-template-columns: 1fr;
  }
}
</style>
