<template>
  <AuthCard
    title="管理员登录"
    badge="管理入口"
    switch-text="返回用户登录"
    :switch-to="{ name: 'login' }"
  >
    <form class="auth-form" @submit.prevent="submit">
      <FormInput v-model="form.phone" label="管理员手机号" placeholder="请输入管理员手机号" />
      <FormInput v-model="form.password" label="密码" type="password" placeholder="请输入密码" />
      <p v-if="message" class="feedback">{{ message }}</p>
      <button class="primary-button submit-button" type="submit" :disabled="submitting">
        {{ submitting ? '登录中...' : '登录' }}
      </button>
    </form>

    <template #footer>
      <RouterLink :to="{ name: 'home' }">返回首页</RouterLink>
    </template>
  </AuthCard>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import AuthCard from '@/components/AuthCard.vue';
import FormInput from '@/components/FormInput.vue';
import { useAuthStore } from '@/store/auth';

const authStore = useAuthStore();
const router = useRouter();
const submitting = ref(false);
const message = ref('');
const form = reactive({ phone: '', password: '' });

const submit = async () => {
  submitting.value = true;
  message.value = '';
  try {
    await authStore.loginAsAdmin(form);
    message.value = '管理员身份已登录，正在进入管理工作台。';
    window.setTimeout(() => {
      router.push({ name: 'admin-dashboard' });
    }, 500);
  } catch (error) {
    message.value = error?.message || '管理员登录失败，请稍后再试。';
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
.auth-form {
  display: grid;
  gap: 16px;
}

.submit-button {
  width: 100%;
  justify-content: center;
}

.feedback {
  margin: 0;
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(224, 239, 248, 0.78);
  color: var(--brand-deep);
}
</style>
