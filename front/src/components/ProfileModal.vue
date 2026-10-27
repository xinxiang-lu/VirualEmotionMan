<template>
  <div v-if="visible" class="modal-mask" @click.self="handleClose">
    <section class="modal-panel card-surface">
      <header class="modal-header">
        <div>
          <h2>个人信息</h2>
          <p>{{ isEditing ? '编辑完成后保存即可更新个人资料。' : '先查看当前资料，确认后再进入编辑。' }}</p>
        </div>
        <button class="close-button" type="button" @click="handleClose">关闭</button>
      </header>

      <section v-if="!isEditing" class="profile-view">
        <div class="avatar-display">
          <span class="avatar-circle">
            <img v-if="form.avatarUrl" :src="form.avatarUrl" alt="用户头像" class="avatar-image" />
            <template v-else>{{ avatarText }}</template>
          </span>
          <div class="avatar-copy">
            <strong>{{ form.nickname || form.phone || '未命名用户' }}</strong>
            <span>{{ form.phone || '暂未填写手机号' }}</span>
          </div>
        </div>

        <div class="profile-grid">
          <article class="info-card">
            <span class="info-label">昵称</span>
            <strong>{{ form.nickname || '未填写' }}</strong>
          </article>
          <article class="info-card">
            <span class="info-label">手机号</span>
            <strong>{{ form.phone || '未填写' }}</strong>
          </article>
          <article class="info-card">
            <span class="info-label">性别</span>
            <strong>{{ genderLabel || '未填写' }}</strong>
          </article>
          <article class="info-card">
            <span class="info-label">年龄</span>
            <strong>{{ form.age || '未填写' }}</strong>
          </article>
          <article class="info-card">
            <span class="info-label">职业</span>
            <strong>{{ form.job || '未填写' }}</strong>
          </article>
          <article class="info-card info-card-wide">
            <span class="info-label">使用目的</span>
            <div v-if="displayPurposes.length" class="purpose-tags">
              <span v-for="item in displayPurposes" :key="item" class="purpose-tag">{{ item }}</span>
            </div>
            <strong v-else>未填写</strong>
          </article>
        </div>

        <div class="form-actions">
          <button class="ghost-button" type="button" @click="handleClose">关闭</button>
          <button class="primary-button" type="button" @click="startEdit">编辑信息</button>
        </div>
      </section>

      <form v-else class="profile-form" @submit.prevent="submit">
        <button class="avatar-panel" type="button" :disabled="uploadingAvatar || saving" @click="triggerAvatarUpload">
          <span class="avatar-circle">
            <img v-if="form.avatarUrl" :src="form.avatarUrl" alt="用户头像" class="avatar-image" />
            <template v-else>{{ avatarText }}</template>
          </span>
          <div class="avatar-copy">
            <strong>{{ form.nickname || form.phone || '未命名用户' }}</strong>
            <span>
              {{
                uploadingAvatar
                  ? '头像上传中...'
                  : form.avatarUrl
                    ? '点击头像可重新上传 JPG 文件'
                    : '点击头像上传 JPG 文件'
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

        <div class="profile-grid">
          <FormInput v-model="form.nickname" label="昵称" placeholder="请输入昵称" />
          <FormInput v-model="form.phone" label="手机号" placeholder="请输入手机号" />
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

        <section class="purpose-block">
          <div class="section-head">
            <h3>使用目的</h3>
            <p>可多选，也可以补充你自己的使用目的。</p>
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

        <p v-if="message" class="feedback">{{ message }}</p>

        <div class="form-actions">
          <button class="ghost-button" type="button" :disabled="saving" @click="cancelEdit">取消编辑</button>
          <button class="primary-button" type="submit" :disabled="saving || uploadingAvatar">
            {{ saving ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { uploadAvatar } from '@/api/auth';
import FormInput from '@/components/FormInput.vue';

const props = defineProps({
  visible: { type: Boolean, default: false },
  profile: { type: Object, default: () => ({}) },
  saving: { type: Boolean, default: false },
});

const emit = defineEmits(['close', 'save']);

const purposeOptions = [
  { label: '情绪倾诉', value: '情绪倾诉' },
  { label: '压力缓解', value: '压力缓解' },
  { label: '日常陪伴', value: '日常陪伴' },
  { label: '心理疏导辅助', value: '心理疏导辅助' },
];

const genderOptions = [
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
  { label: '其他', value: 'other' },
  { label: '不方便透露', value: 'unknown' },
];

const genderMap = {
  male: '男',
  female: '女',
  other: '其他',
  unknown: '不方便透露',
};

const defaultPurposeValues = purposeOptions.map((item) => item.value);
const avatarInput = ref(null);
const uploadingAvatar = ref(false);
const isEditing = ref(false);
const message = ref('');
const form = reactive({
  nickname: '',
  phone: '',
  gender: '',
  age: '',
  job: '',
  purposes: [],
  customPurpose: '',
  avatarUrl: '',
});

const avatarText = computed(() => (form.nickname || form.phone || '心').slice(0, 1));
const genderLabel = computed(() => genderMap[form.gender] || '');
const displayPurposes = computed(() => {
  const values = [...form.purposes];
  if (form.customPurpose.trim()) {
    values.push(...form.customPurpose.split('、').map((item) => item.trim()).filter(Boolean));
  }
  return values;
});

const syncForm = (profile = {}) => {
  const purposeList = Array.isArray(profile.purposeList) ? profile.purposeList : [];
  form.nickname = profile.nickname || '';
  form.phone = profile.phone || '';
  form.gender = profile.gender || '';
  form.age = profile.age ?? '';
  form.job = profile.job || '';
  form.purposes = purposeList.filter((item) => defaultPurposeValues.includes(item));
  form.customPurpose = purposeList.filter((item) => !defaultPurposeValues.includes(item)).join('、');
  form.avatarUrl = profile.avatarUrl || '';
  message.value = '';
};

watch(
  () => props.visible,
  (visible) => {
    if (!visible) return;
    isEditing.value = false;
    syncForm(props.profile);
  },
  { immediate: true },
);

watch(
  () => props.profile,
  (profile) => {
    if (props.saving) {
      syncForm(profile);
      isEditing.value = false;
      return;
    }
    if (isEditing.value) return;
    syncForm(profile);
  },
  { deep: true },
);

const handleClose = () => {
  isEditing.value = false;
  syncForm(props.profile);
  emit('close');
};

const startEdit = () => {
  isEditing.value = true;
  message.value = '';
};

const cancelEdit = () => {
  isEditing.value = false;
  syncForm(props.profile);
};

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

const submit = () => {
  if (!form.nickname.trim()) {
    message.value = '昵称不能为空。';
    return;
  }

  if (!form.phone.trim()) {
    message.value = '手机号不能为空。';
    return;
  }

  emit('save', {
    nickname: form.nickname,
    phone: form.phone,
    gender: form.gender,
    age: form.age,
    job: form.job,
    purposes: form.purposes,
    customPurpose: form.customPurpose,
    avatarUrl: form.avatarUrl,
  });
};
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(48, 61, 67, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.modal-panel {
  width: min(860px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 24px;
}

.modal-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}

.modal-header h2 {
  margin: 0;
  color: var(--text-main);
}

.modal-header p {
  margin: 10px 0 0;
  color: var(--text-soft);
}

.close-button {
  border: none;
  background: transparent;
  color: var(--text-soft);
}

.profile-view,
.profile-form {
  margin-top: 20px;
  display: grid;
  gap: 18px;
}

.avatar-display,
.avatar-panel {
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
  padding: 16px 18px;
  text-align: left;
}

.avatar-circle {
  width: 64px;
  height: 64px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(135deg, #c2dcf5, #d6ead9);
  color: var(--text-main);
  font-size: 1.2rem;
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

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.info-card,
.purpose-block {
  display: grid;
  gap: 10px;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
  padding: 18px;
}

.info-card strong {
  color: var(--text-main);
  font-size: 1rem;
}

.info-card-wide {
  grid-column: 1 / -1;
}

.info-label {
  color: var(--text-soft);
  font-size: 0.9rem;
}

.section-head {
  display: grid;
  gap: 6px;
}

.section-head h3 {
  margin: 0;
  color: var(--text-main);
}

.section-head p {
  margin: 0;
  color: var(--text-soft);
}

.purpose-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.purpose-item,
.purpose-tag {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  padding: 0.9rem 1rem;
  color: var(--text-main);
}

.purpose-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.purpose-tag {
  padding: 0.55rem 0.9rem;
}

.feedback {
  margin: 0;
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(224, 239, 248, 0.78);
  color: var(--brand-deep);
}

.form-actions {
  display: flex;
  justify-content: end;
  gap: 12px;
}

@media (max-width: 768px) {
  .avatar-display,
  .avatar-panel,
  .profile-grid,
  .purpose-grid {
    grid-template-columns: 1fr;
  }

  .avatar-display,
  .avatar-panel {
    display: grid;
    justify-items: start;
  }

  .form-actions {
    display: grid;
  }
}
</style>

