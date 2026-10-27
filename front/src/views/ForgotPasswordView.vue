<template>
  <AuthCard
    title="忘记密码"
    badge="找回账户"
  >
    <form class="auth-form" @submit.prevent="submit">
      <div class="inline-row">
        <FormInput
          v-model="form.phone"
          class="grow"
          label="手机号"
          placeholder="请输入手机号"
        />
        <button class="soft-button code-button" type="button" @click="getCode">
          获取验证码
        </button>
      </div>

      <FormInput
        v-model="form.password"
        label="新密码"
        type="password"
        placeholder="请输入新密码"
      />

      <p v-if="message" class="feedback">{{ message }}</p>

      <button class="primary-button submit-button" type="submit">
        确认
      </button>
    </form>

    <template #footer>
      <RouterLink :to="{ name: 'login' }">返回登录</RouterLink>
    </template>
  </AuthCard>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { requestResetCode, resetPassword } from '@/api/auth';
import AuthCard from '@/components/AuthCard.vue';
import FormInput from '@/components/FormInput.vue';

const message = ref('');
const verificationCode = ref('');
const form = reactive({
  phone: '',
  password: '',
});

const getCode = async () => {
  try {
    const data = await requestResetCode({ phone: form.phone });
    verificationCode.value = data.verification_code || '';
    message.value = verificationCode.value
      ? `验证码已生成，开发模式验证码：${verificationCode.value}`
      : '验证码已发送，请查收。';
  } catch (error) {
    message.value = error?.message || '验证码获取失败，请稍后再试。';
  }
};

const submit = async () => {
  try {
    await resetPassword({
      phone: form.phone,
      password: form.password,
      code: verificationCode.value,
    });
    message.value = '密码重置成功，请返回登录页重新登录。';
  } catch (error) {
    message.value = error?.message || '密码重置失败，请稍后再试。';
  }
};
</script>

<style scoped>
.auth-form {
  display: grid;
  gap: 16px;
}

.inline-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: end;
}

.grow {
  min-width: 0;
}

.code-button,
.submit-button {
  justify-content: center;
}

.feedback {
  margin: 0;
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(224, 239, 248, 0.78);
  color: var(--brand-deep);
}

@media (max-width: 640px) {
  .inline-row {
    grid-template-columns: 1fr;
  }
}
</style>
