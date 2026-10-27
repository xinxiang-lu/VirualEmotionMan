<template>
  <section class="settings-page">
    <article class="settings-card settings-card--wide card-surface">
      <div class="card-head">
        <div>
          <h2>默认 2D 数字人形象</h2>
          <p>未单独设置个人形象的用户，会优先使用这里的默认数字人。</p>
        </div>
      </div>

      <div class="avatar-summary">
        <span class="summary-label">当前默认</span>
        <strong>{{ activeDigitalHumanLabel }}</strong>
        <span class="summary-key">{{ activeDigitalHumanCode }}</span>
      </div>

      <div class="avatar-options">
        <button
          v-for="item in digitalHumanOptions"
          :key="item.code"
          :class="['avatar-option', item.code === activeDigitalHumanCode ? 'is-active' : '']"
          type="button"
          :disabled="switchingDigitalHuman"
          @click="switchDigitalHuman(item.code)"
        >
          <div class="avatar-copy">
            <div class="avatar-copy-top">
              <strong>{{ item.label }}</strong>
              <span v-if="item.code === activeDigitalHumanCode" class="active-pill">默认中</span>
            </div>
            <span>{{ item.code }}</span>
            <p>{{ item.description }}</p>
          </div>
        </button>
      </div>
    </article>

    <article class="settings-card settings-card--wide card-surface">
      <div class="card-head">
        <div>
          <h2>系统默认提示词</h2>
          <p>未配置个人提示词的用户，会直接继承这里的全局聊天规则。</p>
        </div>
        <button class="ghost-button" type="button" @click="openPromptEditor">编辑</button>
      </div>

      <div class="field-box">
        {{ settings.promptTemplate || '未设置系统默认提示词' }}
      </div>
    </article>

    <article class="settings-card settings-card--wide card-surface">
      <div class="card-head">
        <div>
          <h2>用户画像模板</h2>
          <p>管理员可配置需要收集的画像字段。刷新用户画像时，系统会基于历史对话按这些字段整理；新增字段默认显示为“无”。</p>
        </div>
        <button class="ghost-button" type="button" :disabled="savingProfileTemplate" @click="saveProfileTemplate">
          {{ savingProfileTemplate ? '保存中...' : '保存模板' }}
        </button>
      </div>

      <div class="template-meta">
        <label>
          <span>模板名称</span>
          <input v-model="profileTemplateDraft.name" class="template-input" placeholder="用户动态心理画像模板" />
        </label>
        <label>
          <span>模板说明</span>
          <input v-model="profileTemplateDraft.description" class="template-input" placeholder="说明这些字段用于什么场景" />
        </label>
      </div>

      <div class="template-field-list">
        <div v-for="(field, index) in profileTemplateDraft.fields" :key="field.localId" class="template-field">
          <label>
            <span>字段 key</span>
            <input v-model="field.key" class="template-input" placeholder="academic_status" />
          </label>
          <label>
            <span>展示名称</span>
            <input v-model="field.label" class="template-input" placeholder="学业状态" />
          </label>
          <label>
            <span>类型</span>
            <select v-model="field.type" class="template-input">
              <option value="text">文本</option>
              <option value="list">列表</option>
            </select>
          </label>
          <label class="template-field-desc">
            <span>收集说明</span>
            <textarea v-model="field.description" class="template-input" rows="2" placeholder="告诉 AI 这个字段应该记录什么"></textarea>
          </label>
          <button class="remove-field-button" type="button" @click="removeProfileField(index)">删除</button>
        </div>
      </div>

      <button class="add-field-button" type="button" @click="addProfileField">新增画像字段</button>
    </article>

    <PromptEditModal
      :visible="showPromptEditor"
      :prompt="editingPrompt"
      title="编辑系统默认提示词"
      description="这里维护的是系统级默认聊天提示词。保存后，未配置个人提示词的用户会直接使用这套默认规则。"
      @close="showPromptEditor = false"
      @save="savePromptTemplate"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { fetchSystemSettings, updateSystemSettings } from '@/api/admin';
import PromptEditModal from '@/components/PromptEditModal.vue';
import { normalizeLive2dModelCode } from '@/config/live2dModels';

const DEFAULT_DIGITAL_HUMAN_OPTIONS = [
  {
    code: 'haru',
    label: 'Haru',
    description: '更柔和、安静，适合作为默认陪伴形象。',
  },
  {
    code: 'hiyori',
    label: 'Hiyori Momose',
    description: '更轻快、明亮，适合作为活泼风格的默认形象。',
  },
];

const DEFAULT_PROFILE_TEMPLATE = {
  version: 'v3_simplified',
  name: '用户动态心理画像模板',
  description: '定义管理员刷新用户画像时，系统需要从历史对话中整理的核心字段。当前版本保持精简，优先服务演示和复核。',
  fields: {
    basic_background: { label: '基础个人信息', type: 'text', description: '昵称、账号、性别、年龄、身份/职业，以及历史对话中补充出现的稳定背景信息。' },
    use_purpose: { label: '使用目的', type: 'list', description: '用户使用系统的主要目的，例如情绪陪伴、学习压力支持、人际困扰、睡眠改善等。' },
    academic_status: { label: '学业状态', type: 'text', description: '课程、考试、成绩、学习效率、学业挫败等信息。' },
    emotion_pattern: { label: '情绪模式', type: 'text', description: '近期主要情绪、触发因素和波动特点。' },
    risk_signals: { label: '风险信号', type: 'list', description: '需要持续观察或人工介入的风险线索。' },
    recent_context: { label: '近期关键背景', type: 'list', description: '最近对话中对理解用户状态很重要的事实或表达。' },
    sleep_and_body: { label: '睡眠与身体状态', type: 'text', description: '入睡、早醒、睡眠质量、疲惫、食欲、身体不适等信息。' },
    main_stressors: { label: '主要压力源', type: 'list', description: '近期反复出现或对状态影响明显的压力来源。' },
    intervention_preferences: { label: '干预偏好', type: 'list', description: '用户偏好的陪伴方式、称呼、沟通风格、有效策略和无效策略。' },
  },
};

const createDefaultSettings = () => ({
  defaultDigitalHuman: {
    activeCode: DEFAULT_DIGITAL_HUMAN_OPTIONS[0].code,
    options: DEFAULT_DIGITAL_HUMAN_OPTIONS,
  },
  promptTemplate: '',
  profileMemoryTemplate: DEFAULT_PROFILE_TEMPLATE,
});

const createProfileTemplateDraft = (template = DEFAULT_PROFILE_TEMPLATE) => ({
  version: template.version || `custom_${Date.now()}`,
  name: template.name || DEFAULT_PROFILE_TEMPLATE.name,
  description: template.description || DEFAULT_PROFILE_TEMPLATE.description,
  fields: Object.entries(template.fields || {}).map(([key, field], index) => ({
    localId: `${key}-${index}-${Date.now()}`,
    key,
    label: field.label || key,
    type: field.type === 'list' ? 'list' : 'text',
    description: field.description || '',
  })),
});

const settings = ref(createDefaultSettings());
const showPromptEditor = ref(false);
const editingPrompt = ref('');
const switchingDigitalHuman = ref(false);
const savingProfileTemplate = ref(false);
const profileTemplateDraft = ref(createProfileTemplateDraft());

const syncSettings = (payload = {}) => {
  const nextSettings = createDefaultSettings();
  nextSettings.promptTemplate = payload.promptTemplate || '';
  nextSettings.profileMemoryTemplate = payload.profileMemoryTemplate || DEFAULT_PROFILE_TEMPLATE;

  const defaultDigitalHuman = payload.defaultDigitalHuman || {};
  const options =
    Array.isArray(defaultDigitalHuman.options) && defaultDigitalHuman.options.length >= 2
      ? defaultDigitalHuman.options
      : DEFAULT_DIGITAL_HUMAN_OPTIONS;
  const activeCode = normalizeLive2dModelCode(
    defaultDigitalHuman.activeCode || options[0]?.code || DEFAULT_DIGITAL_HUMAN_OPTIONS[0].code,
  );

  nextSettings.defaultDigitalHuman = {
    activeCode,
    options,
  };
  settings.value = nextSettings;
  profileTemplateDraft.value = createProfileTemplateDraft(nextSettings.profileMemoryTemplate);
};

const digitalHumanOptions = computed(
  () =>
    (settings.value.defaultDigitalHuman?.options || DEFAULT_DIGITAL_HUMAN_OPTIONS).map((item) => ({
      ...item,
      code: normalizeLive2dModelCode(item.code),
    })),
);
const activeDigitalHumanCode = computed(
  () => settings.value.defaultDigitalHuman?.activeCode || DEFAULT_DIGITAL_HUMAN_OPTIONS[0].code,
);
const activeDigitalHumanLabel = computed(
  () =>
    digitalHumanOptions.value.find((item) => normalizeLive2dModelCode(item.code) === activeDigitalHumanCode.value)
      ?.label || activeDigitalHumanCode.value,
);

const switchDigitalHuman = async (code) => {
  const normalizedCode = normalizeLive2dModelCode(code);
  if (!normalizedCode || normalizedCode === activeDigitalHumanCode.value || switchingDigitalHuman.value) return;

  switchingDigitalHuman.value = true;
  try {
    const data = await updateSystemSettings({
      defaultDigitalHuman: {
        activeCode: normalizedCode,
      },
    });
    syncSettings(data.settings);
  } catch (error) {
    window.alert(error?.message || '默认数字人切换失败，请稍后再试。');
  } finally {
    switchingDigitalHuman.value = false;
  }
};

const openPromptEditor = () => {
  editingPrompt.value = settings.value.promptTemplate || '';
  showPromptEditor.value = true;
};

const savePromptTemplate = async (value) => {
  try {
    const data = await updateSystemSettings({ promptTemplate: value });
    syncSettings(data.settings);
    showPromptEditor.value = false;
  } catch (error) {
    window.alert(error?.message || '系统默认提示词保存失败，请稍后再试。');
  }
};

const addProfileField = () => {
  profileTemplateDraft.value.fields.push({
    localId: `field-${Date.now()}-${profileTemplateDraft.value.fields.length}`,
    key: '',
    label: '',
    type: 'text',
    description: '',
  });
};

const removeProfileField = (index) => {
  profileTemplateDraft.value.fields.splice(index, 1);
};

const buildProfileTemplatePayload = () => {
  const fields = {};
  profileTemplateDraft.value.fields.forEach((field) => {
    const key = String(field.key || '').trim();
    if (!key) return;
    fields[key] = {
      label: String(field.label || key).trim(),
      type: field.type === 'list' ? 'list' : 'text',
      description: String(field.description || '').trim(),
    };
  });
  return {
    version: `custom_${Date.now()}`,
    name: String(profileTemplateDraft.value.name || DEFAULT_PROFILE_TEMPLATE.name).trim(),
    description: String(profileTemplateDraft.value.description || '').trim(),
    fields,
  };
};

const saveProfileTemplate = async () => {
  const payload = buildProfileTemplatePayload();
  if (!Object.keys(payload.fields).length) {
    window.alert('至少保留一个画像字段。');
    return;
  }

  savingProfileTemplate.value = true;
  try {
    const data = await updateSystemSettings({ profileMemoryTemplate: payload });
    syncSettings(data.settings);
  } catch (error) {
    window.alert(error?.message || '用户画像模板保存失败，请稍后再试。');
  } finally {
    savingProfileTemplate.value = false;
  }
};

onMounted(async () => {
  try {
    const data = await fetchSystemSettings();
    syncSettings(data.settings);
  } catch (error) {
    window.alert(error?.message || '系统设置加载失败，请稍后再试。');
  }
});
</script>

<style scoped>
.settings-page {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.settings-card {
  padding: 20px;
  display: grid;
  gap: 16px;
}

.settings-card--wide {
  grid-column: 1 / -1;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.settings-card h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 1.08rem;
}

.settings-card p {
  margin: 6px 0 0;
  color: var(--text-soft);
  line-height: 1.75;
}

.field-box {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  padding: 16px;
  color: var(--text-main);
  white-space: pre-wrap;
  line-height: 1.8;
  min-height: 80px;
}

.template-meta {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: 12px;
}

.template-meta label,
.template-field label {
  display: grid;
  gap: 6px;
  color: var(--text-soft);
  font-size: 0.82rem;
  font-weight: 700;
}

.template-input {
  width: 100%;
  border: 1px solid rgba(122, 158, 178, 0.2);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.86);
  color: var(--text-main);
  padding: 10px 12px;
  outline: none;
  resize: vertical;
}

.template-input:focus {
  border-color: rgba(43, 125, 116, 0.36);
  box-shadow: 0 0 0 3px rgba(43, 125, 116, 0.08);
}

.template-field-list {
  display: grid;
  gap: 12px;
}

.template-field {
  display: grid;
  grid-template-columns: minmax(130px, 0.7fr) minmax(140px, 0.8fr) 110px minmax(220px, 1.2fr) auto;
  gap: 10px;
  align-items: end;
  border: 1px solid rgba(122, 158, 178, 0.16);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  padding: 14px;
}

.template-field-desc {
  min-width: 0;
}

.remove-field-button,
.add-field-button {
  border: 1px solid rgba(122, 158, 178, 0.2);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--text-soft);
  cursor: pointer;
  font-weight: 800;
  padding: 10px 12px;
}

.remove-field-button:hover,
.add-field-button:hover {
  border-color: rgba(43, 125, 116, 0.34);
  color: var(--brand-deep);
}

.add-field-button {
  justify-self: start;
  background: rgba(43, 125, 116, 0.08);
  color: var(--brand-deep);
}

.field-label,
.summary-label {
  color: var(--text-soft);
  font-size: 0.84rem;
}

.field-box strong,
.avatar-summary strong {
  color: var(--text-main);
  font-size: 1rem;
}

.avatar-summary {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.summary-key {
  padding: 0.18rem 0.56rem;
  border-radius: 999px;
  background: rgba(122, 158, 178, 0.12);
  color: var(--text-soft);
  font-size: 0.78rem;
}

.avatar-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.avatar-option {
  border: 1px solid rgba(122, 158, 178, 0.18);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  min-height: 104px;
  padding: 16px 18px;
  text-align: left;
  display: block;
  transition: border-color 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
}

.avatar-option:hover:not(:disabled) {
  border-color: rgba(122, 158, 178, 0.3);
  transform: translateY(-1px);
}

.avatar-option.is-active {
  border-color: rgba(122, 158, 178, 0.45);
  background: rgba(224, 237, 248, 0.88);
  box-shadow: 0 12px 24px rgba(122, 158, 178, 0.14);
}

.avatar-option:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.avatar-copy {
  min-width: 0;
  display: grid;
  gap: 12px;
  align-content: start;
}

.avatar-copy-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.avatar-copy strong {
  color: var(--text-main);
  font-size: 1rem;
}

.avatar-copy span {
  color: var(--text-soft);
  font-size: 0.8rem;
}

.avatar-copy p {
  margin: 0;
  color: var(--text-soft);
  line-height: 1.65;
}

.active-pill {
  padding: 0.16rem 0.52rem;
  border-radius: 999px;
  background: rgba(90, 126, 147, 0.12);
  color: var(--brand-deep);
  font-size: 0.74rem;
  font-weight: 700;
}

@media (max-width: 1024px) {
  .settings-page {
    grid-template-columns: 1fr;
  }

  .avatar-options {
    grid-template-columns: 1fr;
  }

  .template-meta,
  .template-field {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .card-head { display: grid; }

  .avatar-option {
    min-height: 96px;
    padding: 14px 16px;
  }
}
</style>
