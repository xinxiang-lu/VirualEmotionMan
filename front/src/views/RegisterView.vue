<template>
  <AuthCard title="注册" badge="欢迎加入心陪陪">
    <form class="auth-form" @submit.prevent="submit">
      <div class="register-layout">
        <section class="panel-block">
          <div class="panel-head">
            <h2>基础信息</h2>
            <p>先填写昵称、手机号和基础画像。</p>
          </div>

          <button class="avatar-preview" type="button" :disabled="uploadingAvatar" @click="triggerAvatarUpload">
            <span class="avatar-circle">
              <img v-if="form.avatarUrl" :src="form.avatarUrl" alt="头像预览" class="avatar-image" />
              <template v-else>{{ avatarText }}</template>
            </span>
            <div class="avatar-copy">
              <strong>头像预览</strong>
              <span>
                {{
                  uploadingAvatar
                    ? '正在上传头像...'
                    : form.avatarUrl
                      ? '点击头像可重新上传 JPG 文件'
                      : '点击圆形头像上传 JPG 文件'
                }}
              </span>
            </div>
          </button>

          <input
            ref="avatarInput"
            class="avatar-input"
            type="file"
            hidden
            tabindex="-1"
            aria-hidden="true"
            accept=".jpg,.jpeg,image/jpeg"
            @change="handleAvatarChange"
          />

          <div class="form-grid">
            <FormInput v-model="form.nickname" label="昵称" placeholder="请输入昵称" />
            <FormInput v-model="form.phone" label="手机号" placeholder="请输入手机号" />
            <FormInput v-model="form.password" label="密码" type="password" placeholder="请输入密码" />
            <FormInput
              v-model="form.confirmPassword"
              label="确认密码"
              type="password"
              placeholder="请再次输入密码"
            />
            <FormInput
              v-model="form.gender"
              label="性别"
              type="select"
              :options="genderOptions"
              placeholder="请选择性别"
            />
            <FormInput v-model="form.age" label="年龄" type="number" placeholder="请输入年龄" />
            <FormInput v-model="form.job" label="职业" placeholder="请输入职业" />
          </div>
        </section>

        <section class="panel-block">
          <div class="panel-head">
            <h2>使用目的</h2>
            <p>可多选，也可以补充自己的使用目的。</p>
          </div>

          <div class="purpose-grid">
            <label v-for="option in purposeOptions" :key="option.value" class="purpose-item">
              <input
                type="checkbox"
                :value="option.value"
                :checked="form.purposes.includes(option.value)"
                @change="togglePurpose(option.value)"
              />
              <span>{{ option.label }}</span>
            </label>
          </div>

          <FormInput
            v-model="form.customPurpose"
            label="自定义目的"
            placeholder="例如：失恋支持、考研陪伴、社交练习等"
          />
        </section>
      </div>

      <p v-if="message" class="feedback">{{ message }}</p>

      <button class="primary-button submit-button" type="submit" :disabled="submitting || uploadingAvatar">
        {{ submitting ? '注册中...' : '注册' }}
      </button>
    </form>

    <template #footer>
      <RouterLink :to="{ name: 'login' }">返回登录</RouterLink>
    </template>
  </AuthCard>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { uploadAvatar } from '@/api/auth';
import AuthCard from '@/components/AuthCard.vue';
import FormInput from '@/components/FormInput.vue';
import { useAuthStore } from '@/store/auth';

const authStore = useAuthStore();
const router = useRouter();

const submitting = ref(false);
const uploadingAvatar = ref(false);
const message = ref('');
const avatarInput = ref(null);

const form = reactive({
  nickname: '',
  phone: '',
  avatarUrl: '',
  password: '',
  confirmPassword: '',
  gender: '',
  age: '',
  job: '',
  purposes: [],
  customPurpose: '',
});

const avatarText = computed(() => (form.nickname || '心').slice(0, 1));

const genderOptions = [
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
  { label: '其他', value: 'other' },
  { label: '不方便透露', value: 'unknown' },
];

const purposeOptions = [
  { label: '情绪倾诉', value: '情绪倾诉' },
  { label: '压力缓解', value: '压力缓解' },
  { label: '日常陪伴', value: '日常陪伴' },
  { label: '心理疏导辅助', value: '心理疏导辅助' },
];

const triggerAvatarUpload = () => {
  if (!avatarInput.value) return;
  avatarInput.value.value = '';
  avatarInput.value.click();
};

const handleAvatarChange = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!['jpg', 'jpeg'].includes(extension || '')) {
    message.value = '头像仅支持 JPG 或 JPEG 文件。';
    return;
  }

  uploadingAvatar.value = true;
  message.value = '';

  try {
    const data = await uploadAvatar(file);
    form.avatarUrl = data.avatarUrl || '';
  } catch (error) {
    message.value = error?.message || '头像上传失败，请稍后再试。';
  } finally {
    uploadingAvatar.value = false;
  }
};

const togglePurpose = (value) => {
  if (form.purposes.includes(value)) {
    form.purposes = form.purposes.filter((item) => item !== value);
    return;
  }
  form.purposes = [...form.purposes, value];
};

const submit = async () => {
  if (form.password !== form.confirmPassword) {
    message.value = '两次输入的密码不一致，请重新确认。';
    return;
  }

  if (!form.purposes.length && !form.customPurpose.trim()) {
    message.value = '请至少选择一个使用目的，或填写自定义目的。';
    return;
  }

  if (uploadingAvatar.value) {
    message.value = '头像还在上传中，请稍候再提交注册。';
    return;
  }

  submitting.value = true;
  message.value = '';

  try {
    await authStore.register({
      nickname: form.nickname,
      password: form.password,
      phone: form.phone,
      avatarUrl: form.avatarUrl,
      gender: form.gender,
      age: form.age,
      job: form.job,
      purposes: form.purposes,
      customPurpose: form.customPurpose,
    });
    message.value = '注册成功，正在返回登录页。';
    window.setTimeout(() => {
      router.push({ name: 'login' });
    }, 600);
  } catch (error) {
    message.value = error?.message || '注册失败，请稍后再试。';
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
:deep(.auth-card) {
  width: min(980px, 100%);
}

.auth-form {
  display: grid;
  gap: 18px;
}

.register-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.95fr);
  gap: 20px;
  align-items: start;
}

.panel-block {
  display: grid;
  gap: 14px;
  min-height: 100%;
  border: 1px solid var(--line-soft);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.56);
  padding: 20px;
}

.panel-head {
  display: grid;
  gap: 6px;
}

.panel-head h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 1.05rem;
}

.panel-head p {
  margin: 0;
  color: var(--text-soft);
  line-height: 1.6;
}

.avatar-preview {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.74);
  padding: 14px 16px;
  text-align: left;
}

.avatar-preview:disabled {
  opacity: 0.72;
  cursor: wait;
}

.avatar-circle {
  width: 56px;
  height: 56px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(135deg, #c2dcf5, #d6ead9);
  color: var(--text-main);
  font-size: 1.05rem;
  font-weight: 700;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-copy {
  display: grid;
  gap: 4px;
}

.avatar-copy strong {
  color: var(--text-main);
}

.avatar-copy span {
  color: var(--text-soft);
  font-size: 0.9rem;
}

.avatar-input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.purpose-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.purpose-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  padding: 0.9rem 1rem;
  color: var(--text-main);
}

.purpose-item input {
  margin: 0;
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

@media (max-width: 900px) {
  .register-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>


