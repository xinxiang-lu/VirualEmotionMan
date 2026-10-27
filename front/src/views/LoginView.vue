<template>
  <AuthCard
    title="用户登录"
    badge="欢迎回来"
    switch-text="以管理员身份登录"
    :switch-to="{ name: 'admin-login' }"
  >
    <form class="auth-form" @submit.prevent="submit">
      <FormInput v-model="form.phone" label="手机号" placeholder="请输入手机号" />
      <FormInput v-model="form.password" label="密码" type="password" placeholder="请输入密码" />
      <p v-if="message" class="feedback">{{ message }}</p>
      <button class="primary-button submit-button" type="submit" :disabled="submitting">
        {{ submitting ? '登录中...' : '登录' }}
      </button>
    </form>

    <template #footer>
      <RouterLink :to="{ name: 'register' }">注册</RouterLink>
      <RouterLink :to="{ name: 'forgot-password' }">忘记密码</RouterLink>
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
    await authStore.login(form);
    message.value = '用户登录成功，正在进入主工作台。';
    window.setTimeout(() => router.push({ name: 'chat' }), 500);
  } catch (error) {
    message.value = error?.message || '登录失败，请稍后再试。';
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
